<?php
/**
 * PSR-4 Autoloader for SnippenSMS namespace
 *
 * @package SnippenSMS
 */

spl_autoload_register(
	function ( $class ) {
		$prefix   = 'SnippenSMS\\';
		$base_dir = __DIR__ . '/inc/';

		$len = strlen( $prefix );
		if ( 0 !== strncmp( $prefix, $class, $len ) ) {
			return;
		}

		$relative_class = substr( $class, $len );
		$file           = $base_dir . str_replace( '\\', '/', $relative_class ) . '.php';

		if ( file_exists( $file ) ) {
			require_once $file;
		}
	}
);

