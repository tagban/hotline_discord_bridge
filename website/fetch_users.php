<?php
header("Cache-Control: no-store, no-cache, must-revalidate, max-age=0");
header("Pragma: no-cache");
require_once __DIR__ . '/config.php';

$sql = "SELECT username, source, icon_id FROM online_users WHERE last_seen > DATE_SUB(NOW(), INTERVAL 15 MINUTE) ORDER BY username ASC";
$result = $conn->query($sql);

echo "<h3 style='color:#444; border-bottom:1px solid #1a1a1a; padding-bottom:5px; margin-bottom:10px;'>ENTITIES</h3>";

if ($result && $result->num_rows > 0) {
    while($row = $result->fetch_assoc()) {
        $source = $row['source'];
        $name = htmlspecialchars($row['username']);
        $icon_id = !empty($row['icon_id']) ? $row['icon_id'] : 128;
        
        // Use logic-based defaults for non-hotline sources if icon_id is still 128
        if ($icon_id == 128) {
            if ($source === "Discord") $icon_id = 134;
            if ($source === "Web") $icon_id = 131;
        }

        $icon_url = "http://hlwiki.com/ik0ns/" . $icon_id . ".png";
        $class = strtolower($source) . "-entry";

        echo "<div class='user-row $class' style='position:relative; height:34px; display:flex; align-items:center; margin-bottom:6px; padding-left:28px;'>
                <img src='$icon_url' class='bg-icon' style='position:absolute; left:2px; height:30px; opacity:0.5; z-index:1;' onerror=\"this.src='http://hlwiki.com/ik0ns/128.png';\">
                <span class='user-name' style='position:relative; z-index:2; font-weight:bold;'>$name</span>
              </div>";
    }
}
?>