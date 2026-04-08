<?php
header("Cache-Control: no-store, no-cache, must-revalidate, max-age=0");
header("Pragma: no-cache");
require_once __DIR__ . '/config.php';

function render_terminal_text($text) {
    $text = htmlspecialchars_decode($text);

    // 1. Linkify standard URLs
    $text = preg_replace('!(https?://[a-z0-9_./?=&-]+)!i', '<a href="$1" target="_blank" style="color:#0088ff;">$1</a>', $text);

    // 2. Render Discord Emojis
    $emoji_pattern = '/<a href="(https:\/\/cdn\.discordapp\.com\/emojis\/[0-9]+\.(?:gif|webp|png|jpg|jpeg)[^"]*)"[^>]*>.*?<\/a>/i';
    $emoji_replace = '<img src="$1" class="discord-emoji" style="height:22px; width:auto; vertical-align:middle; margin:0 2px;">';
    $text = preg_replace($emoji_pattern, $emoji_replace, $text);

    // 3. Render Image Thumbnails
    $img_pattern = '/(?<!class="discord-emoji" src=")<a href="(https?:\/\/.*\.(?:png|jpg|jpeg|gif|webp))"[^>]*>.*?<\/a>/i';
    $img_replace = '<br><img src="$1" class="chat-img" style="max-width:300px; border:1px solid #333; margin-top:5px;">';
    return preg_replace($img_pattern, $img_replace, $text);
}

// Auto-purge older than 7 days
$conn->query("DELETE FROM chat_logs WHERE timestamp < DATE_SUB(NOW(), INTERVAL 7 DAY)");

// Select based on your structure: id, source, author, timestamp, message, processed
$sql = "SELECT source, author, message, timestamp FROM chat_logs ORDER BY timestamp DESC LIMIT 60";
$result = $conn->query($sql);

if ($result && $result->num_rows > 0) {
    $rows = [];
    while($row = $result->fetch_assoc()) { $rows[] = $row; }
    $rows = array_reverse($rows);

    foreach($rows as $row) {
        $time = date("H:i", strtotime($row['timestamp']));
        $author = htmlspecialchars($row['author']);
        $source = $row['source'];
        $msg = render_terminal_text($row['message']);
        
        $color = "#00ff00"; // Web Default
        if ($source === "Hotline") $color = "#ff0000";
        elseif ($source === "Discord") $color = "#7289da";

        echo "<div style='margin-bottom:8px; line-height:1.4; font-family:\"Courier New\", monospace;'>
                <span style='color:#444;'>[$time]</span> 
                <span style='color:$color; font-weight:bold;'>$author:</span> 
                <span style='color:#ccc;'>$msg</span>
              </div>";
    }
} else {
    echo "<div style='color:#222; font-style:italic;'>NO_DATA_STREAM_FOUND...</div>";
}
?>