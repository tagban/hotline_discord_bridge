<?php
require_once __DIR__ . '/config.php';
?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title><?php echo $config['discord_activity_name']; ?> // LIVE_MONITOR</title>
    <link rel="stylesheet" href="style.css?v=<?php echo time(); ?>">
    <style>
        .chat-container {
            display: flex !important;
            height: 92vh;
            margin: 20px auto;
            border: 1px solid #1a1a1a;
            background: #000;
        }
        #chat-viewport {
            flex: 1;
            overflow-y: auto;
            padding: 15px;
            border-right: 1px solid #1a1a1a;
        }
        #user-list {
            width: 240px;
            padding: 15px;
            background: #080808;
        }
    </style>
</head>
<body>

<div class="chat-container">
    <div id="chat-viewport">
        <div style="color: #444;">ESTABLISHING_UPLINK...</div>
    </div>
    <div id="user-list">
        <div style="color: #444;">SCANNING...</div>
    </div>
</div>

<script>
    // Initial call
    refreshAll();
    // Refresh every 3 seconds
    setInterval(refreshAll, 3000);

    function refreshAll() {
        // Generate a unique timestamp to bypass browser caching
        const cacheBuster = "?t=" + new Date().getTime();

        // Update Chat
        fetch('fetch_chat.php' + cacheBuster)
            .then(r => r.text())
            .then(data => {
                const v = document.getElementById('chat-viewport');
                const isAtBottom = v.scrollHeight - v.clientHeight <= v.scrollTop + 100;
                v.innerHTML = data;
                if (isAtBottom) v.scrollTop = v.scrollHeight;
            });

        // Update Users
        fetch('fetch_users.php' + cacheBuster)
            .then(r => r.text())
            .then(data => {
                document.getElementById('user-list').innerHTML = data;
            });
    }
</script>
</body>
</html>