<?php
/**
 * Plugin Name: AI Paper in Pillole - Importa articoli
 * Description: Il sito va a prendere da solo gli articoli del podcast su GitHub e li pubblica. Serve perché il firewall di Tophost blocca i server di GitHub quando sono loro a cercare il sito.
 * Version: 1.1.0
 * Author: Sovietaly SRLS
 *
 * Come funziona, in breve:
 * - ogni 6 ore (alle 4, 10, 16 e 22, ora del sito) guarda le ultime puntate nell'archivio del repository GitHub;
 * - se una puntata ha l'articolo ma non risulta pubblicata, la pubblica
 *   con titolo, estratto, categoria, tag e immagine in evidenza;
 * - poi scrive nel repository il file wordpress.json, così la catena notturna
 *   sa che l'articolo è online e non riprova.
 * Non crea doppioni: prima cerca l'articolo con il codice arXiv del paper.
 */

if (!defined('ABSPATH')) {
    exit;
}

const AIPP_OPZIONI = 'aipp_importa';
const AIPP_EVENTO = 'aipp_importa_evento';

function aipp_opzioni() {
    return wp_parse_args(get_option(AIPP_OPZIONI, array()), array(
        'token' => '',
        'repo' => 'sovietalysrls-ui/ai-paper-in-pillole',
        'stato' => 'publish',
        'registro' => array(),
    ));
}

/* ------------------------------------------------------------------ */
/*  Ogni 15 minuti                                                     */
/* ------------------------------------------------------------------ */

add_filter('cron_schedules', function ($s) {
    $s['aipp_6_ore'] = array('interval' => 6 * HOUR_IN_SECONDS, 'display' => 'Ogni 6 ore');
    return $s;
});

/** Il prossimo orario tra le 4, le 10, le 16 e le 22 (ora del sito). */
function aipp_prossimo_orario() {
    $tz = wp_timezone();
    $ora = new DateTime('now', $tz);
    foreach (array(0, 1) as $giorni) {
        foreach (array(4, 10, 16, 22) as $h) {
            $t = new DateTime('today', $tz);
            $t->modify("+$giorni day")->setTime($h, 0);
            if ($t > $ora) {
                return $t->getTimestamp();
            }
        }
    }
    return time() + 6 * HOUR_IN_SECONDS;
}

function aipp_programma() {
    $evento = wp_get_scheduled_event(AIPP_EVENTO);
    if ($evento && $evento->schedule === 'aipp_6_ore') {
        return;
    }
    // Nessun controllo programmato, o programmato con il vecchio intervallo.
    wp_clear_scheduled_hook(AIPP_EVENTO);
    wp_schedule_event(aipp_prossimo_orario(), 'aipp_6_ore', AIPP_EVENTO);
}

register_activation_hook(__FILE__, 'aipp_programma');

register_deactivation_hook(__FILE__, function () {
    wp_clear_scheduled_hook(AIPP_EVENTO);
});

add_action('init', 'aipp_programma');

add_action(AIPP_EVENTO, 'aipp_importa');

/* ------------------------------------------------------------------ */
/*  GitHub                                                             */
/* ------------------------------------------------------------------ */

function aipp_github($metodo, $percorso, $corpo = null, $grezzo = false) {
    $o = aipp_opzioni();
    if (!$o['token']) {
        return new WP_Error('aipp', 'manca il token GitHub nelle impostazioni');
    }
    $args = array(
        'method' => $metodo,
        'timeout' => 60,
        'headers' => array(
            'Authorization' => 'Bearer ' . $o['token'],
            'Accept' => $grezzo ? 'application/vnd.github.raw' : 'application/vnd.github+json',
            'User-Agent' => 'AIPP-Importa',
            'X-GitHub-Api-Version' => '2022-11-28',
        ),
    );
    if ($corpo !== null) {
        $args['body'] = wp_json_encode($corpo);
        $args['headers']['Content-Type'] = 'application/json';
    }
    $r = wp_remote_request('https://api.github.com/repos/' . $o['repo'] . $percorso, $args);
    if (is_wp_error($r)) {
        return $r;
    }
    $codice = wp_remote_retrieve_response_code($r);
    $testo = wp_remote_retrieve_body($r);
    if ($codice >= 400) {
        return new WP_Error('aipp', "GitHub $codice su $percorso: " . substr($testo, 0, 200), $codice);
    }
    return $grezzo ? $testo : json_decode($testo, true);
}

function aipp_file($cartella, $nome, $grezzo = true) {
    return aipp_github('GET', '/contents/archivio/puntate/' . rawurlencode($cartella) . '/' . $nome . '?ref=main', null, $grezzo);
}

/* ------------------------------------------------------------------ */
/*  Importazione                                                       */
/* ------------------------------------------------------------------ */

function aipp_scrivi_registro($righe) {
    $o = aipp_opzioni();
    $o['registro'] = array_slice(array_merge($righe, $o['registro']), 0, 30);
    update_option(AIPP_OPZIONI, $o, false);
}

function aipp_importa() {
    if (get_transient('aipp_in_corso')) {
        return array('già in corso');
    }
    set_transient('aipp_in_corso', 1, 600);
    $righe = array();
    $ora = wp_date('d/m H:i');
    try {
        $elenco = aipp_github('GET', '/contents/archivio/puntate?ref=main');
        if (is_wp_error($elenco)) {
            $righe[] = "$ora · " . $elenco->get_error_message();
            return $righe;
        }
        $cartelle = array();
        foreach ($elenco as $voce) {
            if ($voce['type'] === 'dir') {
                $cartelle[] = $voce['name'];
            }
        }
        sort($cartelle);
        foreach (array_slice($cartelle, -5) as $c) {
            $righe = array_merge($righe, aipp_importa_cartella($c, $ora));
        }
        if (!$righe) {
            $righe[] = "$ora · controllo fatto, niente di nuovo";
        }
    } finally {
        delete_transient('aipp_in_corso');
        aipp_scrivi_registro($righe);
    }
    return $righe;
}

function aipp_importa_cartella($c, $ora) {
    // Già pubblicato (dalla catena notturna o da questo plugin)?
    $wpjson = aipp_file($c, 'wordpress.json', false);
    if (!is_wp_error($wpjson)) {
        return array();
    }
    if ($wpjson->get_error_data() !== 404) {
        return array("$ora · $c: " . $wpjson->get_error_message());
    }
    $html = aipp_file($c, 'articolo.html');
    if (is_wp_error($html)) {
        return $html->get_error_data() === 404 ? array() : array("$ora · $c: " . $html->get_error_message());
    }
    $meta = aipp_file($c, 'articolo_meta.json');
    $meta = is_wp_error($meta) ? array() : json_decode($meta, true);
    $titolo = isset($meta['titolo']) ? $meta['titolo'] : $c;

    // Chiave anti-doppione: il codice arXiv, come fa la catena notturna.
    $chiave = preg_match('#arxiv\.org/abs/([\w.]+)#', $html, $m) ? $m[1] : $titolo;
    $id = aipp_trova($chiave, $c);
    $esisteva = (bool) $id;
    $o = aipp_opzioni();

    if (!$id) {
        $categoria = isset($meta['categoria']) ? $meta['categoria'] : 'AI Paper in Pillole';
        $id_cat = get_cat_ID($categoria);
        if (!$id_cat) {
            $t = wp_insert_term($categoria, 'category');
            $id_cat = is_wp_error($t) ? 0 : $t['term_id'];
        }
        $admin = get_users(array('role' => 'administrator', 'number' => 1, 'fields' => 'ids'));
        $id = wp_insert_post(array(
            'post_author' => $admin ? $admin[0] : 1,
            'post_title' => wp_strip_all_tags($titolo),
            'post_content' => $html,
            'post_excerpt' => isset($meta['estratto']) ? $meta['estratto'] : '',
            'post_status' => $o['stato'],
            'post_category' => $id_cat ? array($id_cat) : array(),
            'tags_input' => isset($meta['tag']) ? array_slice($meta['tag'], 0, 6) : array(),
            'meta_input' => array('_aipp_cartella' => $c),
        ), true);
        if (is_wp_error($id)) {
            return array("$ora · $c: articolo non creato: " . $id->get_error_message());
        }
        aipp_copertina($c, $id, $titolo);
    } elseif ($o['stato'] === 'publish' && get_post_status($id) === 'draft') {
        wp_update_post(array('ID' => $id, 'post_status' => 'publish'));
    }

    // Avvisa la catena notturna: l'articolo è online.
    $esito = array(
        'id' => $id,
        'link' => get_permalink($id),
        'stato' => get_post_status($id),
        'esisteva' => $esisteva,
        'da' => 'plugin del sito',
    );
    $scritto = aipp_github('PUT', '/contents/archivio/puntate/' . rawurlencode($c) . '/wordpress.json', array(
        'message' => "Archivio: articolo pubblicato dal sito ($c)",
        'content' => base64_encode(wp_json_encode($esito, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES) . "\n"),
        'branch' => 'main',
    ));
    $nota = is_wp_error($scritto) ? ' (ma non sono riuscito ad avvisare GitHub: ' . $scritto->get_error_message() . ')' : '';
    return array("$ora · $c: " . ($esisteva ? 'era già sul sito' : 'pubblicato') . ' → ' . get_permalink($id) . $nota);
}

function aipp_trova($chiave, $cartella) {
    $q = get_posts(array(
        'post_type' => 'post', 'post_status' => array('publish', 'draft', 'future', 'pending'),
        'meta_key' => '_aipp_cartella', 'meta_value' => $cartella, 'fields' => 'ids', 'numberposts' => 1,
    ));
    if ($q) {
        return $q[0];
    }
    $q = get_posts(array(
        'post_type' => 'post', 'post_status' => array('publish', 'draft', 'future', 'pending'),
        's' => $chiave, 'numberposts' => 5,
    ));
    foreach ($q as $p) {
        if (strpos($p->post_content, $chiave) !== false) {
            return $p->ID;
        }
    }
    return 0;
}

function aipp_copertina($c, $id_post, $titolo) {
    $dati = aipp_file($c, 'copertina.jpg');
    if (is_wp_error($dati) || !$dati) {
        return;
    }
    require_once ABSPATH . 'wp-admin/includes/image.php';
    $f = wp_upload_bits(sanitize_file_name($c) . '.jpg', null, $dati);
    if (!empty($f['error'])) {
        return;
    }
    $id_media = wp_insert_attachment(array(
        'post_mime_type' => 'image/jpeg',
        'post_title' => wp_strip_all_tags($titolo),
        'post_status' => 'inherit',
    ), $f['file'], $id_post);
    if (is_wp_error($id_media)) {
        return;
    }
    wp_update_attachment_metadata($id_media, wp_generate_attachment_metadata($id_media, $f['file']));
    update_post_meta($id_media, '_wp_attachment_image_alt', wp_strip_all_tags($titolo));
    set_post_thumbnail($id_post, $id_media);
}

/* ------------------------------------------------------------------ */
/*  Pagina delle impostazioni: Impostazioni > AI Paper in Pillole      */
/* ------------------------------------------------------------------ */

add_action('admin_menu', function () {
    add_options_page('AI Paper in Pillole', 'AI Paper in Pillole', 'manage_options', 'aipp-importa', 'aipp_pagina');
});

function aipp_pagina() {
    if (!current_user_can('manage_options')) {
        return;
    }
    $o = aipp_opzioni();
    $esito = array();
    if (isset($_POST['aipp_salva']) && check_admin_referer('aipp')) {
        $token = trim(sanitize_text_field(wp_unslash($_POST['token'])));
        if ($token !== '') {
            $o['token'] = $token;
        }
        $o['repo'] = trim(sanitize_text_field(wp_unslash($_POST['repo'])));
        $o['stato'] = $_POST['stato'] === 'draft' ? 'draft' : 'publish';
        update_option(AIPP_OPZIONI, $o, false);
        echo '<div class="notice notice-success"><p>Impostazioni salvate.</p></div>';
    }
    if (isset($_POST['aipp_ora']) && check_admin_referer('aipp')) {
        $esito = aipp_importa();
        $o = aipp_opzioni();
    }
    $prossimo = wp_next_scheduled(AIPP_EVENTO);
    ?>
    <div class="wrap">
        <h1>AI Paper in Pillole</h1>
        <p>Alle 4, alle 10, alle 16 e alle 22 il sito controlla su GitHub se c'è un articolo nuovo e lo pubblica da solo.</p>
        <form method="post">
            <?php wp_nonce_field('aipp'); ?>
            <table class="form-table">
                <tr><th>Token GitHub</th><td>
                    <input type="password" name="token" class="regular-text" placeholder="<?php echo $o['token'] ? 'salvato (lascia vuoto per non cambiarlo)' : 'incolla qui il token'; ?>">
                </td></tr>
                <tr><th>Repository</th><td><input type="text" name="repo" class="regular-text" value="<?php echo esc_attr($o['repo']); ?>"></td></tr>
                <tr><th>Stato</th><td>
                    <select name="stato">
                        <option value="publish" <?php selected($o['stato'], 'publish'); ?>>Pubblica subito</option>
                        <option value="draft" <?php selected($o['stato'], 'draft'); ?>>Lascia in bozza</option>
                    </select>
                </td></tr>
            </table>
            <p>
                <button class="button button-primary" name="aipp_salva" value="1">Salva</button>
                <button class="button" name="aipp_ora" value="1">Controlla adesso</button>
            </p>
        </form>
        <?php if ($esito) : ?>
            <h2>Risultato</h2>
            <ul><?php foreach ($esito as $r) { echo '<li>' . esc_html($r) . '</li>'; } ?></ul>
        <?php endif; ?>
        <h2>Ultimi controlli</h2>
        <p>Prossimo controllo automatico: <?php echo $prossimo ? esc_html(wp_date('d/m H:i', $prossimo)) : 'non programmato'; ?></p>
        <ul><?php foreach ($o['registro'] as $r) { echo '<li>' . esc_html($r) . '</li>'; } ?></ul>
    </div>
    <?php
}
