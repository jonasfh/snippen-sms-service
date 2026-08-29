<?php
/**
 * Plugin Name: Snippen SMS Service
 * Plugin URI: https://github.com/jonasfh/snippen-sms-service
 * Description: SMS service plugin for Snippen Booking.
 * Version: 0.1.0
 * Author: Snippen
 * Author URI: https://github.com/jonasfh
 * Text Domain: snippen-sms
 * Domain Path: /languages
 * Requires at least: 6.0
 * Requires PHP: 7.4
 *
 * @package SnippenSMS
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit; // Exit if accessed directly.
}

define( 'SNIPPEN_SMS_VERSION', '0.1.0' );
define( 'SNIPPEN_SMS_FILE', __FILE__ );
define( 'SNIPPEN_SMS_PATH', plugin_dir_path( __FILE__ ) );
define( 'SNIPPEN_SMS_URL', plugin_dir_url( __FILE__ ) );

// Load Composer autoloader if available, otherwise fall back to custom autoloader.
if ( file_exists( __DIR__ . '/../../../../vendor/autoload.php' ) ) {
	require_once __DIR__ . '/../../../../vendor/autoload.php';
} elseif ( file_exists( SNIPPEN_SMS_PATH . 'autoloader.php' ) ) {
	require_once SNIPPEN_SMS_PATH . 'autoloader.php';
}

/**
 * Initialize the plugin.
 */
function snippen_sms_init() {
	if ( class_exists( 'SnippenSMS\\Plugin' ) ) {
		\SnippenSMS\Plugin::get_instance()->init();
	}
}
add_action( 'plugins_loaded', 'snippen_sms_init' );

