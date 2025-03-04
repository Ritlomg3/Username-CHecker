import asyncio
import aiohttp
import time
import requests
from datetime import datetime
import pytz
import re
from wordfreq import word_frequency

# Define the Discord webhook URLs
notifier_webhook_url = "s"
commands_webhook_url = "s"

# Discord bot token (required to listen for messages)
DISCORD_BOT_TOKEN = "s"  # Replace with your bot token
DISCORD_CHANNEL_ID = "s"  # Channel for commands

# Bot status variables
start_time = time.time()  # Track bot runtime
usernames_checked = 0  # Track usernames checked
total_usernames = 0  # Total usernames to check
valid_count = 0  # Valid usernames
inappropriate_count = 0  # Inappropriate usernames
erased_count = 0  # Erased usernames
taken_count = 0  # Taken usernames

# New variables for frequency and bulk notifier
frequency_notifier_on = True
bulk_notifier_on = True
bulk_notifier_set = 104
bulk_results = []  # Stores results when bulk notifier is on

url = 'https://users.roblox.com/v1/usernames/users'
validate_url = 'https://auth.roblox.com/v1/usernames/validate'
headers = {
    'accept': 'application/json',
    'Content-Type': 'application/json'
}

rate_limited_accounts = []
retry_accounts = []
sem = asyncio.Semaphore(26)  # Limit rate-limited checks to 26 simultaneously

def is_username_valid(username):
    """
    Check if a username is valid based on Roblox's rules:
    - Must be between 3 and 20 characters long.
    - Can only contain letters, numbers, and underscores.
    """
    if not (3 <= len(username) <= 20):
        return False
    if not re.match(r'^[a-zA-Z0-9_]+$', username):
        return False
    return True

async def fetch_user_data(username, session):
    global usernames_checked, valid_count, inappropriate_count, erased_count, taken_count, bulk_results
    result = f"Checking {username}"  # Initialize result with a default value

    # Skip invalid usernames
    if not is_username_valid(username):
        print(f"Skipping invalid username: {username}")
        with open('invalid.txt', 'a') as file:
            file.write(f"{username}\n")  # Log invalid usernames to invalid.txt
        return

    data = {
        "usernames": [
            username
        ],
        "excludeBannedUsers": False
    }
    retries = 3
    while retries > 0:
        try:
            async with sem:
                async with session.post(url, headers=headers, json=data) as response:
                    if response.status == 200:
                        user_data = (await response.json()).get("data", [])
                        if user_data:
                            user_id = user_data[0].get("id", 0)
                            result = f"{username} - {user_id}"
                            # Save user ID and username to "sorted.txt"
                            with open('sorted.txt', 'a') as file:
                                file.write(f"{user_id} - {username}\n")
                            taken_count += 1
                            if bulk_notifier_on:
                                bulk_results.append((username, "Taken", user_id))  # Add to bulk results
                            # Do NOT send notifications for taken usernames when bulkn is off
                        else:
                            # Check if the username is inappropriate or erased
                            username_status, emoji = await check_username_status(username)
                            if username_status == "Valid":
                                valid_count += 1
                                with open('output.txt', 'a') as file:
                                    file.write(f"{username}\n")  # Save ONLY valid usernames to output.txt
                                if fping_on:  # Check frequency if fping is on
                                    freq = word_frequency(username, 'en')
                                    if freq > 0:  # Ping @everyone if frequency is above 0
                                        send_discord_webhook(notifier_webhook_url, username, "Valid", ping_everyone=True, frequency=freq)
                                if bulk_notifier_on:
                                    bulk_results.append((username, "Valid", "N/A"))  # Add to bulk results
                                else:
                                    send_discord_webhook(notifier_webhook_url, username, username_status, ping_everyone=False)
                                result = f"{username} - Valid"
                            elif username_status == "Inappropriate":
                                inappropriate_count += 1
                                if bulk_notifier_on:
                                    bulk_results.append((username, "Inappropriate", "N/A"))  # Add to bulk results
                                else:
                                    send_discord_webhook(notifier_webhook_url, username, username_status, ping_everyone=False)
                                result = f"{username} - Inappropriate"
                            else:
                                # If not valid or inappropriate, mark as erased
                                erased_count += 1
                                if bulk_notifier_on:
                                    bulk_results.append((username, "Erased", "N/A"))  # Add to bulk results
                                else:
                                    send_discord_webhook(notifier_webhook_url, username, "Erased", ping_everyone=True)
                                result = f"{username} - Erased"
                    elif response.status == 429:  # Rate limit error
                        result = f"Rate limited for {username}. Will retry later."
                        print(result)
                        rate_limited_accounts.append(username)  # Add to the current list of rate-limited accounts
                        break
                    else:
                        result = f"Failed to check {username}"
                    print(result)
                    usernames_checked += 1
                    break
        except aiohttp.ClientError as e:
            result = f"Error fetching data for {username}: {e}. Retrying..."
            print(result)
            retries -= 1
            if retries == 0:
                result = f"Failed to fetch data for {username} after 3 retries."
                print(result)
            await asyncio.sleep(5)  # Wait before retrying
        except Exception as e:
            result = f"Unexpected error for {username}: {e}"
            print(result)
            break

    # Check if bulk notifier is on and if we've reached the batch size (26 usernames)
    if bulk_notifier_on and len(bulk_results) >= 26:
        send_bulk_notification()
        bulk_results.clear()  # Reset the results for the next batch

def send_bulk_notification():
    pht_time = datetime.now(pytz.timezone('Asia/Manila')).strftime('%Y-%m-%d %I:%M %p (PHT)')
    description = "```ansi\n"
    valid_usernames = []
    inappropriate_usernames = []
    erased_usernames = []
    taken_usernames = []
    has_erased = False  # Track if there's at least one erased username
    has_freq_valid = False  # Track if there's a valid username with frequency > 0

    for username, status, user_id in bulk_results:
        if status == "Valid":
            freq = word_frequency(username, 'en')  # Get frequency for the username
            if fping_on and freq > 0:  # Highlight valid usernames with frequency > 0
                description += f"\u001b[2;34mfreq valid\u001b[0m - {username} (ID: {user_id}) (Frequency: {freq:.10f})\n"
                has_freq_valid = True
            else:
                description += f"\u001b[2;32mvalid\u001b[0m - {username} (ID: {user_id})\n"
            valid_usernames.append(username)
        elif status == "Inappropriate":
            description += f"\u001b[2;31minappropriate\u001b[0m - {username} (ID: {user_id})\n"
            inappropriate_usernames.append(username)
        elif status == "Erased":
            description += f"\u001b[2;40merased\u001b[0m - {username} (ID: {user_id})\n"
            erased_usernames.append(username)
            has_erased = True  # Set to True if there's at least one erased username
        elif status == "Taken":
            description += f"\u001b[2;33mtaken\u001b[0m - {username} (ID: {user_id})\n"
            taken_usernames.append(username)

    description += "```"

    embed = {
        "id": 822647868,
        "description": description,
        "fields": [
            {
                "id": 513014176,
                "name": "Valid",
                "value": f"```\n{' '.join(valid_usernames)}\n```",
                "inline": True
            },
            {
                "id": 547003956,
                "name": "Inappropriate",
                "value": f"```\n{' '.join(inappropriate_usernames)}\n```",
                "inline": True
            },
            {
                "id": 270121390,
                "name": "Erased",
                "value": f"```\n{' '.join(erased_usernames)}\n```",
                "inline": True
            },
            {
                "id": 123456789,
                "name": "Taken",
                "value": f"```\n{' '.join(taken_usernames)}\n```",
                "inline": True
            }
        ],
        "color": 8823295,
        "footer": {
            "text": f"{pht_time} (Bulk {usernames_checked // 26})"
        },
        "author": {
            "icon_url": "https://tr.rbxcdn.com/30DAY-AvatarHeadshot-627B6C8BCB74C3DDED26DBB143264003-Png/150/150/AvatarHeadshot/Webp/noFilter",
            "name": "Bulk Notify"
        },
        "title": "Username Status from 26 usernames"
    }

    # Ping @everyone if there's at least one erased username or a valid username with frequency > 0
    content = "||@everyone||" if has_erased or has_freq_valid else ""

    payload = {
        "content": content,  # Ping @everyone if has_erased or has_freq_valid is True
        "tts": False,
        "embeds": [embed],
        "components": [],
        "actions": {}
    }

    headers = { "Content-Type": "application/json" }
    response = requests.post(notifier_webhook_url, json=payload, headers=headers)

    if response.status_code == 204:
        print("Bulk notification sent successfully!")
    else:
        print(f"Failed to send bulk notification. Status code: {response.status_code}")

async def check_username_status(username):
    try:
        url = f"https://auth.roblox.com/v1/usernames/validate?birthday=2006-09-21T07:00:00.000Z&context=Signup&username={username}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                data = await response.json()
                if data["code"] == 0:
                    return "Valid", "🟢"
                elif data["code"] == 1:
                    return "Erased", "⚫"  # Erased usernames (banned and not viewable)
                elif data["code"] == 2:
                    return "Inappropriate", "🔴"
                else:
                    return None, None
    except aiohttp.ClientError as e:
        print(f"Error fetching username status: {e}")
        return None, None
    except Exception as e:
        print(f"Unexpected error: {e}")
        return None, None

def load_usernames_from_file(file_path):
    global total_usernames
    with open(file_path, 'r') as file:
        usernames = [line.strip() for line in file if line.strip()]
        total_usernames = len(usernames)
        return usernames

def send_discord_webhook(webhook_url, username, status, ping_everyone=False, frequency=None):
    # Get current time in Philippine Time (PHT)
    pht_time = datetime.now(pytz.timezone('Asia/Manila')).strftime('%Y-%m-%d %I:%M %p (PHT)')

    # Base embed structure
    embed = {
        "id": 533283178,
        "description": f"A username has been hit\n```{username}```",
        "fields": [],
        "author": {
            "name": "Username Found",
            "icon_url": "https://tr.rbxcdn.com/30DAY-AvatarHeadshot-627B6C8BCB74C3DDED26DBB143264003-Png/150/150/AvatarHeadshot/Webp/noFilter"
        },
        "footer": {
            "text": f"{pht_time} (Status: {status})"
        }
    }

    # Add frequency to footer if frequency is provided
    if frequency is not None:
        embed["footer"]["text"] += f" (Frequency: {frequency:.10f})"

    # Customize embed based on status
    if status == "Valid":
        embed["color"] = 65321  # Green color
        embed["thumbnail"] = {
            "url": "https://cdn.discordapp.com/attachments/1300397208729948221/1344630681505890394/g.png?ex=67c396a8&is=67c24528&hm=92af12f08be76d29868cdafc3be152196234c528ee0ca3bde8b516b851f848c0&"
        }
    elif status == "Inappropriate":
        embed["color"] = 16711680  # Red color
        embed["thumbnail"] = {
            "url": "https://cdn.discordapp.com/attachments/1300397208729948221/1344630475892719648/cross.png?ex=67c39677&is=67c244f7&hm=3dc0cb51e5484502701f3a0c18d46e1597dafeeada66fc3105084b53503aa59c&"
        }
    elif status == "Erased":
        embed["color"] = 8421504  # Grey color
        embed["thumbnail"] = {
            "url": "https://cdn.discordapp.com/attachments/1300397208729948221/1344631182935199755/itsatar.e.png?ex=67c39720&is=67c245a0&hm=6a70bf7feb8d1bad6898b9835f80742657ac232bdc387f17209b4d1f6cbe837e&"
        }

    # Prepare the payload
    payload = {
        "content": "||@everyone||" if ping_everyone else "",  # Ping everyone only if specified
        "tts": False,
        "embeds": [embed],  # Embed goes below the ping
        "components": [],
        "actions": {}
    }

    # Send the webhook
    headers = { "Content-Type": "application/json" }
    response = requests.post(webhook_url, json=payload, headers=headers)

    if response.status_code == 204:
        print("Message sent successfully to Discord webhook!")
    else:
        print(f"Failed to send message. Status code: {response.status_code}")

async def handle_commands(message):
    """
    Handles commands from Discord messages and sends output to the commands channel.
    """
    content = message.get('content', '').strip()
    user_id = message.get('author', {}).get('id')

    if content == "$get output":
        send_file_via_webhook(commands_webhook_url, 'output.txt', user_id)
    elif content == "$get sorted":
        send_file_via_webhook(commands_webhook_url, 'sorted.txt', user_id)
    elif content == "$status":
        send_status_embed(commands_webhook_url)
    elif content == "$cmds":
        send_cmds_embed(commands_webhook_url)
    elif content.startswith("$frequency"):
        handle_frequency_commands(content)
    elif content.startswith("$fping"):
        handle_fping_command(content)
    elif content.startswith("$bulkn"):
        handle_bulkn_commands(content)
    elif content.startswith("$bulknset"):
        handle_bulknset_command(content)

def handle_frequency_commands(content):
    global frequency_notifier_on
    if content == "$frequency list":
        send_frequency_list_embed()
    elif content == "$frequency on":
        frequency_notifier_on = True
        send_frequency_status_embed(True)
    elif content == "$frequency off":
        frequency_notifier_on = False
        send_frequency_status_embed(False)

def send_frequency_list_embed():
    with open('output.txt', 'r') as file:
        usernames = [line.strip() for line in file if line.strip()]
    
    frequency_dict = {username: word_frequency(username, 'en') for username in usernames}
    sorted_frequency = sorted(frequency_dict.items(), key=lambda x: x[1], reverse=True)[:10]  # Top 10
    
    description = "Top 10 usernames by frequency:\n```\n"
    for username, freq in sorted_frequency:
        description += f"{username} - {freq:.10f}\n"
    description += "```"
    
    embed = {
        "id": 18170189,
        "description": description,
        "fields": [],
        "author": {
            "name": "Frequency List",
            "icon_url": "https://tr.rbxcdn.com/30DAY-AvatarHeadshot-627B6C8BCB74C3DDED26DBB143264003-Png/150/150/AvatarHeadshot/Webp/noFilter"
        },
        "color": 12386160,
        "footer": {
            "text": datetime.now(pytz.timezone('Asia/Manila')).strftime('%Y-%m-%d %I:%M %p (PHT)')
        }
    }

    payload = {
        "content": "",
        "tts": False,
        "embeds": [embed],
        "components": [],
        "actions": {}
    }

    headers = { "Content-Type": "application/json" }
    response = requests.post(commands_webhook_url, json=payload, headers=headers)

    if response.status_code == 204:
        print("Frequency list embed sent successfully!")
    else:
        print(f"Failed to send frequency list embed. Status code: {response.status_code}")

def send_frequency_status_embed(status):
    embed = {
        "id": 598828177,
        "description": f"Frequency notification is now\n``` {'ON' if status else 'OFF'} ```",
        "fields": [],
        "color": 16756736,
        "author": {
            "icon_url": "https://tr.rbxcdn.com/30DAY-AvatarHeadshot-627B6C8BCB74C3DDED26DBB143264003-Png/150/150/AvatarHeadshot/Webp/noFilter",
            "name": "Frequency"
        }
    }

    payload = {
        "content": "",
        "tts": False,
        "embeds": [embed],
        "components": [],
        "actions": {}
    }

    headers = { "Content-Type": "application/json" }
    response = requests.post(commands_webhook_url, json=payload, headers=headers)

    if response.status_code == 204:
        print("Frequency status embed sent successfully!")
    else:
        print(f"Failed to send frequency status embed. Status code: {response.status_code}")

def handle_fping_command(content):
    global fping_on
    if content == "$fping on":
        fping_on = True
        send_fping_status_embed(True)
    elif content == "$fping off":
        fping_on = False
        send_fping_status_embed(False)

def send_fping_status_embed(status):
    embed = {
        "id": 598828177,
        "description": f"Frequency notification is now\n``` {'ON' if status else 'OFF'} ```",
        "fields": [],
        "color": 16756736,
        "author": {
            "icon_url": "https://tr.rbxcdn.com/30DAY-AvatarHeadshot-627B6C8BCB74C3DDED26DBB143264003-Png/150/150/AvatarHeadshot/Webp/noFilter",
            "name": "Frequency Notification"
        }
    }

    payload = {
        "content": "",
        "tts": False,
        "embeds": [embed],
        "components": [],
        "actions": {}
    }

    headers = { "Content-Type": "application/json" }
    response = requests.post(commands_webhook_url, json=payload, headers=headers)

    if response.status_code == 204:
        print("Fping status embed sent successfully!")
    else:
        print(f"Failed to send fping status embed. Status code: {response.status_code}")

def handle_bulkn_commands(content):
    global bulk_notifier_on
    if content == "$bulkn on":
        bulk_notifier_on = True
        send_bulkn_status_embed(True)
    elif content == "$bulkn off":
        bulk_notifier_on = False
        send_bulkn_status_embed(False)

def send_bulkn_status_embed(status):
    embed = {
        "id": 598828177,
        "description": f"Bulkn is now\n``` {'ON' if status else 'OFF'} ```",
        "fields": [],
        "color": 16756736,
        "author": {
            "icon_url": "https://tr.rbxcdn.com/30DAY-AvatarHeadshot-627B6C8BCB74C3DDED26DBB143264003-Png/150/150/AvatarHeadshot/Webp/noFilter",
            "name": "Bulkn"
        }
    }

    payload = {
        "content": "",
        "tts": False,
        "embeds": [embed],
        "components": [],
        "actions": {}
    }

    headers = { "Content-Type": "application/json" }
    response = requests.post(commands_webhook_url, json=payload, headers=headers)

    if response.status_code == 204:
        print("Bulkn status embed sent successfully!")
    else:
        print(f"Failed to send bulkn status embed. Status code: {response.status_code}")

def handle_bulknset_command(content):
    global bulk_notifier_set
    try:
        num = int(content.split()[1])
        bulk_notifier_set = num
        send_bulknset_embed(num)
    except (IndexError, ValueError):
        print("Invalid number provided for bulknset.")

def send_bulknset_embed(num):
    embed = {
        "id": 598828177,
        "description": f"Bulkn num is now set to\n-# (104 default)\n```{num}```",
        "fields": [],
        "color": 16756736,
        "author": {
            "icon_url": "https://tr.rbxcdn.com/30DAY-AvatarHeadshot-627B6C8BCB74C3DDED26DBB143264003-Png/150/150/AvatarHeadshot/Webp/noFilter",
            "name": "Bulkn"
        }
    }

    payload = {
        "content": "",
        "tts": False,
        "embeds": [embed],
        "components": [],
        "actions": {}
    }

    headers = { "Content-Type": "application/json" }
    response = requests.post(commands_webhook_url, json=payload, headers=headers)

    if response.status_code == 204:
        print("Bulknset embed sent successfully!")
    else:
        print(f"Failed to send bulknset embed. Status code: {response.status_code}")

def send_cmds_embed(webhook_url):
    """
    Sends the $cmds embed to the specified webhook.
    """
    embed = {
        "id": 822647868,
        "description": "Available Commands:",
        "fields": [
            {
                "id": 376376970,
                "name": "$get",
                "value": "```- $get output (exports output.txt to you)\n- $get sorted (exports sorted.txt to you)```",
                "inline": True
            },
            {
                "id": 23813210,
                "name": "$status",
                "value": "``` - gets further information as well as status of the notifier ```",
                "inline": True
            },
            {
                "id": 254652031,
                "name": "$cmds",
                "value": "``` - shows every commands available in the server. ```"
            },
            {
                "id": 254652032,
                "name": "$frequency",
                "value": "```- $frequency list (shows frequency list)\n- $frequency on/off (turns frequency notifier on/off)```",
                "inline": True
            },
            {
                "id": 254652033,
                "name": "$fping",
                "value": "``` - pings @everyone if a username checked has a word frequency higher than 0 ```",
                "inline": True
            },
            {
                "id": 254652034,
                "name": "$bulkn",
                "value": "```- $bulkn on/off (turns bulk notifier on/off)\n- $bulknset (sets the number of usernames to check before sending a bulk notification)```",
                "inline": True
            }
        ],
        "color": 16750848,
        "footer": {
            "text": datetime.now(pytz.timezone('Asia/Manila')).strftime('%Y-%m-%d %I:%M %p (PHT)')
        },
        "author": {
            "icon_url": "https://tr.rbxcdn.com/30DAY-AvatarHeadshot-627B6C8BCB74C3DDED26DBB143264003-Png/150/150/AvatarHeadshot/Webp/noFilter",
            "name": "Commands List"
        }
    }

    payload = {
        "content": "",
        "tts": False,
        "embeds": [embed],
        "components": [],
        "actions": {}
    }

    headers = { "Content-Type": "application/json" }
    response = requests.post(webhook_url, json=payload, headers=headers)

    if response.status_code == 204:
        print("$cmds embed sent successfully!")
    else:
        print(f"Failed to send $cmds embed. Status code: {response.status_code}")

def send_status_embed(webhook_url):
    """
    Sends the bot status embed to the specified webhook.
    """
    runtime = int(time.time() - start_time)  # Runtime in seconds
    usernames_per_minute = (usernames_checked / runtime) * 60 if runtime > 0 else 0
    usernames_per_hour = usernames_per_minute * 60

    embed = {
        "id": 533283178,
        "fields": [
            {
                "id": 25785485,
                "name": "Current Bot Status",
                "value": f"```\nON\nRuntime: {runtime}s```",
                "inline": True
            },
            {
                "id": 964793302,
                "name": "Usernames in Process",
                "value": f"```{usernames_checked} / {total_usernames} ({int((usernames_checked / total_usernames) * 100)}%)```",
                "inline": True
            },
            {
                "id": 47830560,
                "name": "Checking Speed",
                "value": f"```(PM) {int(usernames_per_minute)} Accs\n(PH) {int(usernames_per_hour)} Accs```",
                "inline": True
            },
            {
                "id": 73525489,
                "name": "Usernames Gathered",
                "value": f"```VALID - {valid_count}\nINAPPROPRIATE - {inappropriate_count}\nERASED - {erased_count}\nTAKEN - {taken_count}```",
                "inline": False
            },
            {
                "id": 528689939,
                "name": "Bot Info",
                "value": "Made by Ofve\n\nPlease note that this bot is only in my possession, **it is NOT available to be distributed by any other**, includes the people I know of.",
                "inline": False
            }
        ],
        "author": {
            "name": "Bot Information",
            "icon_url": "https://tr.rbxcdn.com/30DAY-AvatarHeadshot-627B6C8BCB74C3DDED26DBB143264003-Png/150/150/AvatarHeadshot/Webp/noFilter"
        },
        "color": 16737024,
        "footer": {
            "text": datetime.now(pytz.timezone('Asia/Manila')).strftime('%Y-%m-%d %I:%M %p (PHT)')
        }
    }

    payload = {
        "content": "",
        "tts": False,
        "embeds": [embed],
        "components": [],
        "actions": {}
    }

    headers = { "Content-Type": "application/json" }
    response = requests.post(webhook_url, json=payload, headers=headers)

    if response.status_code == 204:
        print("Status embed sent successfully!")
    else:
        print(f"Failed to send status embed. Status code: {response.status_code}")

async def listen_for_commands():
    """
    Listens for commands in a specific Discord channel.
    """
    headers = {
        "Authorization": f"Bot {DISCORD_BOT_TOKEN}"
    }
    last_message_id = None

    while True:
        try:
            # Fetch the latest messages from the channel
            response = requests.get(
                f"https://discord.com/api/v9/channels/{DISCORD_CHANNEL_ID}/messages",
                headers=headers
            )
            messages = response.json()

            if messages:
                latest_message = messages[0]
                if latest_message['id'] != last_message_id:
                    last_message_id = latest_message['id']
                    await handle_commands(latest_message)

        except Exception as e:
            print(f"Error fetching messages: {e}")

        await asyncio.sleep(5)  # Check for new messages every 5 seconds

async def main():
    usernames = load_usernames_from_file('usernames.txt')
    batch_size = 26
    wait_time = 5  # Changed to 5 seconds
    account_count = 0

    # Start the command listener
    asyncio.create_task(listen_for_commands())

    async with aiohttp.ClientSession() as session:
        while usernames:
            batch_usernames = usernames[:batch_size]
            usernames = usernames[batch_size:]

            await asyncio.gather(*[fetch_user_data(username, session) for username in batch_usernames])

            # Remove checked usernames from usernames.txt
            with open('usernames.txt', 'w') as file:
                file.writelines([f"{username}\n" for username in usernames])

            account_count += batch_size

            if account_count % 104 == 0:
                print(f"Waiting for 10 seconds before the next batch...")
                time.sleep(10)
                wait_time = 5  # Reset wait_time to 5 seconds
            else:
                print(f"Waiting for {wait_time} seconds before the next batch...")
                time.sleep(wait_time)

            # Save rate-limited accounts to ratelimited.txt while script is running
            with open('ratelimited.txt', 'w') as file:
                for account in rate_limited_accounts:
                    file.write(f"{account}\n")

            # Sort and save IDs in "sorted.txt" after each batch
            with open('sorted.txt', 'r') as file:
                ids_and_usernames = [line.strip().split(' - ') for line in file if line.strip()]
            sorted_ids_and_usernames = sorted(ids_and_usernames, key=lambda x: int(x[0]), reverse=True)  # Sort by ID in descending order
            with open('sorted.txt', 'w') as file:
                file.writelines([f"{id} - {username}\n" for id, username in sorted_ids_and_usernames])

asyncio.run(main())
