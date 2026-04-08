<?php
/**
 * BigRedH Bridge - Web Configuration File
 * --------------------------------------
 * This file handles the database connection and global settings
 * for the Web Monitor interface.
 */

$web_config = [
    // --- DATABASE SETTINGS ---
    // The web interface reads chat logs and user lists from this database.
    'db_host'         => 'localhost',
    'db_user'         => 'DATABASE_USER',
    'db_pass'         => 'DATABASE_PASSWORD',
    'db_name'         => 'DATABASE_NAME',
    
    // --- WEBSITE IDENTITY ---
    'site_name'       => 'BigRedH - LIVE',
    'site_url'        => 'https://your-website.com/',
    'hotline_addr'    => 'your-hotline-server.com',
    'discord_invite'  => 'https://discord.gg/yourlink',

    // --- BOT CONNECTIVITY ---
    // This allows the website to talk back to the Python bot.
    // 'bot_url' should point to the IP/Port where bridge_bot.py is running.
    'bot_url'         => 'http://localhost:54230/webhook',
    'web_secret_key'  => 'PASTE_YOUR_WEB_SECRET_KEY_FROM_BOT_CONFIG_HERE',

    // --- UI SETTINGS ---
    'items_to_load'   => 100, // Number of chat messages to show
    'refresh_rate'    => 3000 // How often to poll for new data (in milliseconds)
];

// Map local config to global variable for the fetch scripts
$config = $web_config;

// Establish Database Connection
$conn = new mysqli(
    $config['db_host'],
    $config['db_user'],
    $config['db_pass'],
    $config['db_name']
);

// Check for connection errors
if ($conn->connect_error) {
    header('HTTP/1.1 500 Internal Server Error');
    die("CRITICAL_FAILURE // DB_CONNECTION_LOST: " . $conn->connect_error);
}

// Set charset to utf8mb4 for full emoji and retro character support
$conn->set_charset("utf8mb4");

/**
 * PRO-TIP:
 * Ensure the database user has SELECT, INSERT, and DELETE privileges
 * on the chat_logs and online_users tables.
 */
?>
