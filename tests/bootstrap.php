<?php

/**
 * Bootstrap tests for Snippen SMS Plugin
 */

// Define WordPress constants for testing
if ( ! defined( 'ABSPATH' ) ) {
	define( 'ABSPATH', getenv( 'WP_ABSPATH' ) ?: '/wordpress/' );
}

// Disable automatic WP-Cron execution during test suite loading/execution
if ( ! defined( 'DISABLE_WP_CRON' ) ) {
	define( 'DISABLE_WP_CRON', true );
}

// Load Composer autoloader or fallback to plugin autoloader
if ( file_exists( __DIR__ . '/../vendor/autoload.php' ) ) {
	require_once __DIR__ . '/../vendor/autoload.php';
} elseif ( file_exists( __DIR__ . '/../src/wp-content/plugins/snippen-sms/autoloader.php' ) ) {
	require_once __DIR__ . '/../src/wp-content/plugins/snippen-sms/autoloader.php';
}

// Define test fixtures directory
define( 'SNIPPEN_SMS_TESTS_DIR', __DIR__ );

