This bot now handles emojis well, connects and reconnects, changes username to the user sending from Hotline in Discord, and will search for matching user in discord to use their icon if available.

Config changes:

You can now set prefix/suffix for hardcoded 'admins'. This is via the config file but I found it useful (If you don't you can just set everyone as a user), the admins simply show up with a shield or your chocie of emoji. Color codes are as follows:

Style / Color	admin_prefix	admin_suffix
Orange/Yellow Box	```fix\n	\n```
Cyan/Light Blue Box	```yaml\n	\n```
Light Blue (Alternate)	```bash\n"	"\n```
Red (Warning style)	```diff\n-	\n```
Green (Success style)	```diff\n+	\n```
No Box (Bold only)	**[ADMIN] **	**
Standard Quote	> **[ADMIN]** 	``


TODO: 
  - Event Logging (Connect/Disconnect from server) (Configurable)
  - Commands from Discord/Hotline chat to get information
  
