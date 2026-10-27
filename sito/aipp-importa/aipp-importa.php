<?php
/**
 * Plugin Name: AI Paper in Pillole - Importa articoli
 * Description: Il sito va a prendere da solo gli articoli del podcast su GitHub e li pubblica. Serve perché il firewall di Tophost blocca i server di GitHub quando sono loro a cercare il sito.
 * Version: 1.2.0
 * Requires at least: 5.6
 * Requires PHP: 7.4
 * Author: Sovietaly SRLS
 *
 * Come funziona, in breve:
 * - a orari regolabili (Impostazioni > AI Paper in Pillole) guarda le ultime
 *   puntate nell'archivio del repository GitHub;
 * - se una puntata ha l'articolo ma non risulta pubblicata, la pubblica
 *   con titolo, estratto, categoria, tag e immagine in evidenza;
 * - poi scrive nel repository il file wordpress.json, così la catena notturna
 *   sa che l'articolo è online e non riprova.
 * Non crea doppioni: prima cerca l'articolo con il codice arXiv del paper.
 *
 * Sicurezza:
 * - impostazioni visibili e modificabili solo dagli amministratori, con
 *   protezione contro i moduli falsificati (nonce);
 * - il token non viene mai mostrato nella pagina e viene mandato solo ad
 *   api.github.com, senza seguire rimandi verso altri indirizzi;
 * - il testo che arriva da GitHub viene sempre ripulito (niente script),
 *   l'immagine viene accettata solo se è davvero un JPEG o PNG e sotto 10 MB;
 * - nomi di cartelle e repository vengono controllati prima dell'uso;
 * - disinstallando il plugin si cancellano token e impostazioni.
 */

if (!defined('ABSPATH')) {
    exit;
}

const AIPP_OPZIONI = 'aipp_importa';
const AIPP_EVENTO = 'aipp_importa_evento';
const AIPP_INTERVALLI = array(1, 2, 3, 4, 6, 8, 12, 24);
const AIPP_MAX_IMMAGINE = 10485760; // 10 MB

function aipp_opzioni() {
    $o = get_option(AIPP_OPZIONI, array());
    return wp_parse_args(is_array($o) ? $o : array(), array(
        'token' => '',
        'repo' => 'sovietalysrls-ui/ai-paper-in-pillole',
        'stato' => 'publish',
        'ora_inizio' => '04:00',
        'ogni_ore' => 6,
        'registro' => array(),
    ));
}

function aipp_salva_opzioni($o) {
    // autoload=false: il token non viene caricato in memoria a ogni pagina del sito.
    update_option(AIPP_OPZIONI, $o, false);
}

/* ------------------------------------------------------------------ */
/*  Orari                                                              */
/* ------------------------------------------------------------------ */

add_filter('cron_schedules', function ($s) {
    foreach (AIPP_INTERVALLI as $h) {
        $s['aipp_ogni_' . $h] = array('interval' => $h * HOUR_IN_SECONDS, 'display' => "Ogni $h ore");
    }
    return $s;
});

/** Gli orari del giorno, per esempio 04:00, 10:00, 16:00, 22:00. */
function aipp_orari_del_giorno($o) {
    list($h, $m) = array_map('intval', explode(':', $o['ora_inizio']));
    $passo = (int) $o['ogni_ore'];
    $orari = array();
    for ($i = 0; $i < 24 / $passo; $i++) {
        $orari[] = array(($h + $i * $passo) % 24, $m);
    }
    usort($orari, function ($a, $b) {
        return $a[0] * 60 + $a[1] - ($b[0] * 60 + $b[1]);
    });
    return $orari;
}

function aipp_prossimo_orario($o) {
    $tz = wp_timezone();
    $adesso = new DateTime('now', $tz);
    foreach (array(0, 1) as $giorni) {
        foreach (aipp_orari_del_giorno($o) as $hm) {
            $t = new DateTime('today', $tz);
            $t->modify("+$giorni day")->setTime($hm[0], $hm[1]);
            if ($t > $adesso) {
                return $t->getTimestamp();
            }
        }
    }
    return time() + HOUR_IN_SECONDS;
}

/** Programma i controlli; li riprogramma se gli orari sono cambiati. */
function aipp_programma($forza = false) {
    $o = aipp_opzioni();
    $firma = $o['ora_inizio'] . '|' . $o['ogni_ore'];
    $evento = wp_get_scheduled_event(AIPP_EVENTO);
    if (!$forza && $evento && get_option('aipp_pianificato') === $firma) {
        return;
    }
    wp_clear_scheduled_hook(AIPP_EVENTO);
    wp_schedule_event(aipp_prossimo_orario($o), 'aipp_ogni_' . (int) $o['ogni_ore'], AIPP_EVENTO);
    update_option('aipp_pianificato', $firma, false);
}

register_activation_hook(__FILE__, function () {
    aipp_programma(true);
});

register_deactivation_hook(__FILE__, function () {
    wp_clear_scheduled_hook(AIPP_EVENTO);
    delete_option('aipp_pianificato');
});

register_uninstall_hook(__FILE__, 'aipp_disinstalla');

function aipp_disinstalla() {
    wp_clear_scheduled_hook(AIPP_EVENTO);
    delete_option(AIPP_OPZIONI);
    delete_option('aipp_pianificato');
    delete_transient('aipp_in_corso');
}

add_action('init', function () {
    aipp_programma();
});

add_action(AIPP_EVENTO, 'aipp_importa');

/* ------------------------------------------------------------------ */
/*  GitHub                                                             */
/* ------------------------------------------------------------------ */

function aipp_repo_valido($repo) {
    return (bool) preg_match('#^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$#', $repo);
}

function aipp_cartella_valida($c) {
    return (bool) preg_match('#^[A-Za-z0-9_.-]{1,150}$#', $c) && strpos($c, '..') === false;
}

function aipp_github($metodo, $percorso, $corpo = null, $grezzo = false) {
    $o = aipp_opzioni();
    if (!$o['token']) {
        return new WP_Error('aipp', 'manca il token GitHub nelle impostazioni');
    }
    if (!aipp_repo_valido($o['repo'])) {
        return new WP_Error('aipp', 'nome del repository non valido');
    }
    $args = array(
        'method' => $metodo,
        'timeout' => 60,
        'redirection' => 0,          // il token non deve mai finire su un altro indirizzo
        'sslverify' => true,
        'limit_response_size' => AIPP_MAX_IMMAGINE + 1,
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
        return new WP_Error('aipp', 'GitHub non raggiungibile: ' . $r->get_error_message());
    }
    $codice = (int) wp_remote_retrieve_response_code($r);
    $testo = wp_remote_retrieve_body($r);
    if ($codice >= 300) {
        $spiegazione = array(
            401 => 'token non valido o scaduto',
            403 => 'il token non ha i permessi giusti (serve Contents: Read and write)',
            404 => 'non trovato',
        );
        $msg = isset($spiegazione[$codice]) ? $spiegazione[$codice] : substr(wp_strip_all_tags($testo), 0, 150);
        return new WP_Error('aipp', "GitHub $codice: $msg", $codice);
    }
    return $grezzo ? $testo : json_decode($testo, true);
}

function aipp_file($cartella, $nome, $grezzo = true) {
    return aipp_github('GET', '/contents/archivio/puntate/' . rawurlencode($cartella) . '/' . rawurlencode($nome) . '?ref=main', null, $grezzo);
}

/* ------------------------------------------------------------------ */
/*  Importazione                                                       */
/* ------------------------------------------------------------------ */

function aipp_scrivi_registro($righe) {
    $o = aipp_opzioni();
    $o['registro'] = array_slice(array_merge($righe, (array) $o['registro']), 0, 30);
    aipp_salva_opzioni($o);
}

function aipp_importa() {
    if (get_transient('aipp_in_corso')) {
        return array('un controllo è già in corso');
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
        foreach ((array) $elenco as $voce) {
            if (isset($voce['type'], $voce['name']) && $voce['type'] === 'dir' && aipp_cartella_valida($voce['name'])) {
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
    // Il testo viene sempre ripulito: restano solo i tag ammessi negli articoli.
    $html = wp_kses_post($html);
    $meta = aipp_file($c, 'articolo_meta.json');
    $meta = is_wp_error($meta) ? array() : json_decode($meta, true);
    $meta = is_array($meta) ? $meta : array();
    $titolo = sanitize_text_field(isset($meta['titolo']) ? $meta['titolo'] : $c);
    $estratto = sanitize_textarea_field(isset($meta['estratto']) ? $meta['estratto'] : '');
    $categoria = sanitize_text_field(isset($meta['categoria']) ? $meta['categoria'] : 'AI Paper in Pillole');
    $tag = array();
    foreach (array_slice(isset($meta['tag']) ? (array) $meta['tag'] : array(), 0, 6) as $t) {
        $t = sanitize_text_field($t);
        if ($t !== '') {
            $tag[] = $t;
        }
    }

    // Chiave anti-doppione: il codice arXiv, come fa la catena notturna.
    $chiave = preg_match('#arxiv\.org/abs/([\w.]+)#', $html, $m) ? $m[1] : $titolo;
    $id = aipp_trova($chiave, $c);
    $esisteva = (bool) $id;
    $o = aipp_opzioni();

    if (!$id) {
        $id_cat = get_cat_ID($categoria);
        if (!$id_cat) {
            $t = wp_insert_term($categoria, 'category');
            $id_cat = is_wp_error($t) ? 0 : $t['term_id'];
        }
        $admin = get_users(array('role' => 'administrator', 'number' => 1, 'fields' => 'ids'));
        $id = wp_insert_post(array(
            'post_author' => $admin ? $admin[0] : 1,
            'post_title' => $titolo,
            'post_content' => $html,
            'post_excerpt' => $estratto,
            'post_status' => $o['stato'] === 'draft' ? 'draft' : 'publish',
            'post_category' => $id_cat ? array($id_cat) : array(),
            'tags_input' => $tag,
            'meta_input' => array('_aipp_cartella' => $c),
        ), true);
        if (is_wp_error($id)) {
            return array("$ora · $c: articolo non creato: " . $id->get_error_message());
        }
        $foto = aipp_copertina($c, $id, $titolo);
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
    if (!empty($foto)) {
        $nota .= " (immagine: $foto)";
    }
    return array("$ora · $c: " . ($esisteva ? 'era già sul sito' : 'pubblicato') . ' → ' . get_permalink($id) . $nota);
}

function aipp_trova($chiave, $cartella) {
    $stati = array('publish', 'draft', 'future', 'pending', 'private');
    $q = get_posts(array(
        'post_type' => 'post', 'post_status' => $stati,
        'meta_key' => '_aipp_cartella', 'meta_value' => $cartella, 'fields' => 'ids', 'numberposts' => 1,
    ));
    if ($q) {
        return $q[0];
    }
    $q = get_posts(array('post_type' => 'post', 'post_status' => $stati, 's' => $chiave, 'numberposts' => 5));
    foreach ($q as $p) {
        if (strpos($p->post_content, $chiave) !== false) {
            return $p->ID;
        }
    }
    return 0;
}

/** Restituisce '' se tutto bene, altrimenti il motivo per cui manca l'immagine. */
function aipp_copertina($c, $id_post, $titolo) {
    $dati = aipp_file($c, 'copertina.jpg');
    if (is_wp_error($dati)) {
        return $dati->get_error_message();
    }
    if (!$dati || strlen($dati) > AIPP_MAX_IMMAGINE) {
        return 'vuota o troppo grande';
    }
    // Si accetta solo un'immagine vera, controllando il contenuto e non il nome.
    $info = function_exists('getimagesizefromstring') ? @getimagesizefromstring($dati) : false;
    $tipi = array(IMAGETYPE_JPEG => array('jpg', 'image/jpeg'), IMAGETYPE_PNG => array('png', 'image/png'));
    if (!$info || !isset($tipi[$info[2]])) {
        return 'il file non è un JPEG o PNG valido';
    }
    list($est, $mime) = $tipi[$info[2]];
    require_once ABSPATH . 'wp-admin/includes/image.php';
    $f = wp_upload_bits(sanitize_file_name($c) . '.' . $est, null, $dati);
    if (!empty($f['error'])) {
        return $f['error'];
    }
    $id_media = wp_insert_attachment(array(
        'post_mime_type' => $mime,
        'post_title' => $titolo,
        'post_status' => 'inherit',
    ), $f['file'], $id_post, true);
    if (is_wp_error($id_media)) {
        return $id_media->get_error_message();
    }
    wp_update_attachment_metadata($id_media, wp_generate_attachment_metadata($id_media, $f['file']));
    update_post_meta($id_media, '_wp_attachment_image_alt', $titolo);
    set_post_thumbnail($id_post, $id_media);
    return '';
}

/* ------------------------------------------------------------------ */
/*  Pagina delle impostazioni: Impostazioni > AI Paper in Pillole      */
/* ------------------------------------------------------------------ */

add_action('admin_menu', function () {
    add_options_page('AI Paper in Pillole', 'AI Paper in Pillole', 'manage_options', 'aipp-importa', 'aipp_pagina');
});

function aipp_avviso($testo, $tipo = 'success') {
    echo '<div class="notice notice-' . esc_attr($tipo) . '"><p>' . esc_html($testo) . '</p></div>';
}

function aipp_pagina() {
    if (!current_user_can('manage_options')) {
        wp_die('Non hai i permessi per questa pagina.');
    }
    $o = aipp_opzioni();
    $esito = array();

    if ($_SERVER['REQUEST_METHOD'] === 'POST') {
        check_admin_referer('aipp');
        $azione = isset($_POST['aipp_azione']) ? sanitize_key(wp_unslash($_POST['aipp_azione'])) : '';

        if ($azione === 'salva') {
            $errori = array();
            $token = isset($_POST['token']) ? trim(sanitize_text_field(wp_unslash($_POST['token']))) : '';
            if ($token !== '') {
                if (preg_match('#^[A-Za-z0-9_]{20,255}$#', $token)) {
                    $o['token'] = $token;
                } else {
                    $errori[] = 'Il token non sembra valido: non l\'ho salvato.';
                }
            }
            $repo = isset($_POST['repo']) ? trim(sanitize_text_field(wp_unslash($_POST['repo']))) : '';
            if (aipp_repo_valido($repo)) {
                $o['repo'] = $repo;
            } else {
                $errori[] = 'Il repository deve avere la forma proprietario/nome.';
            }
            $o['stato'] = (isset($_POST['stato']) && $_POST['stato'] === 'draft') ? 'draft' : 'publish';
            $ora = isset($_POST['ora_inizio']) ? sanitize_text_field(wp_unslash($_POST['ora_inizio'])) : '';
            if (preg_match('#^([01]\d|2[0-3]):([0-5]\d)$#', $ora)) {
                $o['ora_inizio'] = $ora;
            } else {
                $errori[] = 'Ora di partenza non valida.';
            }
            $ogni = isset($_POST['ogni_ore']) ? (int) $_POST['ogni_ore'] : 0;
            if (in_array($ogni, AIPP_INTERVALLI, true)) {
                $o['ogni_ore'] = $ogni;
            }
            aipp_salva_opzioni($o);
            aipp_programma(true);
            foreach ($errori as $e) {
                aipp_avviso($e, 'error');
            }
            aipp_avviso('Impostazioni salvate.');
        } elseif ($azione === 'ora') {
            $esito = aipp_importa();
        } elseif ($azione === 'cancella_token') {
            $o['token'] = '';
            aipp_salva_opzioni($o);
            aipp_avviso('Token cancellato.');
        }
        $o = aipp_opzioni();
    }

    $prossimo = wp_next_scheduled(AIPP_EVENTO);
    $orari = array();
    foreach (aipp_orari_del_giorno($o) as $hm) {
        $orari[] = sprintf('%02d:%02d', $hm[0], $hm[1]);
    }
    ?>
    <div class="wrap">
        <h1>AI Paper in Pillole</h1>
        <p>Il sito controlla su GitHub se c'è un articolo nuovo e lo pubblica da solo.</p>
        <p><strong>Orari dei controlli:</strong> <?php echo esc_html(implode(', ', $orari)); ?>.
           <strong>Prossimo:</strong> <?php echo $prossimo ? esc_html(wp_date('d/m H:i', $prossimo)) : 'non programmato'; ?>.</p>
        <form method="post">
            <?php wp_nonce_field('aipp'); ?>
            <table class="form-table" role="presentation">
                <tr><th scope="row"><label for="aipp_ora">Primo controllo alle</label></th><td>
                    <input type="time" id="aipp_ora" name="ora_inizio" value="<?php echo esc_attr($o['ora_inizio']); ?>" required>
                    <p class="description">Ora italiana. Di solito la puntata è pronta tra le 2:30 e le 4.</p>
                </td></tr>
                <tr><th scope="row"><label for="aipp_ogni">Poi ogni</label></th><td>
                    <select id="aipp_ogni" name="ogni_ore">
                        <?php foreach (AIPP_INTERVALLI as $h) : ?>
                            <option value="<?php echo (int) $h; ?>" <?php selected((int) $o['ogni_ore'], $h); ?>><?php echo (int) $h; ?> <?php echo $h === 1 ? 'ora' : 'ore'; ?></option>
                        <?php endforeach; ?>
                    </select>
                </td></tr>
                <tr><th scope="row"><label for="aipp_token">Token GitHub</label></th><td>
                    <input type="password" id="aipp_token" name="token" class="regular-text" autocomplete="off"
                           placeholder="<?php echo $o['token'] ? 'salvato (lascia vuoto per non cambiarlo)' : 'incolla qui il token'; ?>">
                    <p class="description"><?php echo $o['token'] ? 'Un token è salvato. Per sicurezza non viene mai mostrato.' : 'Nessun token salvato.'; ?></p>
                </td></tr>
                <tr><th scope="row"><label for="aipp_repo">Repository</label></th><td>
                    <input type="text" id="aipp_repo" name="repo" class="regular-text" value="<?php echo esc_attr($o['repo']); ?>">
                </td></tr>
                <tr><th scope="row"><label for="aipp_stato">Articoli</label></th><td>
                    <select id="aipp_stato" name="stato">
                        <option value="publish" <?php selected($o['stato'], 'publish'); ?>>Pubblica subito</option>
                        <option value="draft" <?php selected($o['stato'], 'draft'); ?>>Lascia in bozza</option>
                    </select>
                </td></tr>
            </table>
            <p>
                <button class="button button-primary" name="aipp_azione" value="salva">Salva</button>
                <button class="button" name="aipp_azione" value="ora">Controlla adesso</button>
                <?php if ($o['token']) : ?>
                    <button class="button-link-delete" name="aipp_azione" value="cancella_token" style="margin-left:12px">Cancella token</button>
                <?php endif; ?>
            </p>
        </form>
        <?php if ($esito) : ?>
            <h2>Risultato</h2>
            <ul><?php foreach ($esito as $r) { echo '<li>' . esc_html($r) . '</li>'; } ?></ul>
        <?php endif; ?>
        <h2>Ultimi controlli</h2>
        <ul><?php foreach ((array) $o['registro'] as $r) { echo '<li>' . esc_html($r) . '</li>'; } ?></ul>
    </div>
    <?php
}
