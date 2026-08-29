<?php
/**
 * Main Plugin Bootstrapper class for Snippen SMS Service
 *
 * @package SnippenSMS
 */

namespace SnippenSMS;

/**
 * Class Plugin
 */
class Plugin {

	/**
	 * Instance of this class.
	 *
	 * @var Plugin|null
	 */
	private static $instance = null;

	/**
	 * Get instance of the plugin.
	 *
	 * @return Plugin
	 */
	public static function get_instance() {
		if ( null === self::$instance ) {
			self::$instance = new self();
		}
		return self::$instance;
	}

	/**
	 * Initialize plugin hooks and services.
	 */
	public function init() {
		// Register plugin hooks here.
	}
}

