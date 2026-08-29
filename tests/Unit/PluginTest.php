<?php

namespace SnippenSMS\Tests\Unit;

use SnippenSMS\Plugin;
use SnippenSMS\Tests\TestCase;

/**
 * Unit tests for SnippenSMS\Plugin.
 */
class PluginTest extends TestCase {

	/**
	 * Test that get_instance returns a Plugin instance.
	 */
	public function testGetInstanceReturnsPluginInstance() {
		$instance = Plugin::get_instance();
		$this->assertInstanceOf( Plugin::class, $instance );
	}

	/**
	 * Test that get_instance returns the same singleton instance.
	 */
	public function testGetInstanceReturnsSingleton() {
		$instance1 = Plugin::get_instance();
		$instance2 = Plugin::get_instance();
		$this->assertSame( $instance1, $instance2 );
	}
}

