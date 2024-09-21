import asyncio
import aiohttp
import time
import string
import requests

# Define the Discord webhook URL here
webhook_url = "https://discord.com/api/webhooks/1281825017570660362/g6IVnUntyoMq-NLmyjakcQFmrUAQW4wajH7agK8KsSyd_d-w7MvEog4hQrjKcxoiMDjp"

url = 'https://users.roblox.com/v1/usernames/users'
validate_url = 'https://auth.roblox.com/v1/usernames/validate'
headers = {
    'accept': 'application/json',
    'Content-Type': 'application/json'
}

rate_limited_accounts = []
retry_accounts = []
sem = asyncio.Semaphore(26)  # Limit rate-limited checks to 26 simultaneously

async def fetch_user_data(username, session):
    data = {
        "usernames": [
            username
        ],
        "excludeBannedUsers": False
    }
    retries = 3
    while retries > 0:
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
                    else:
                        result = f"{username} - 0"
                        with open('output.txt', 'a') as file:
                            file.write(f"erased: {username}\n")  # Save erased usernames to output.txt
                        # Check if erased account is claimable
                        username_status, emoji = await check_username_status(username)
                        if username_status:
                            with open('available.txt', 'a') as file:
                                file.write(f"{username}\n")  # Save claimable usernames to available.txt
                            send_discord_webhook(webhook_url, username, username_status, emoji)
                elif response.status == 429:  # Rate limit error
                    print(f"Rate limited for {username}. Will retry later.")
                    rate_limited_accounts.append(username)  # Add to the current list of rate-limited accounts
                    break
                else:
                    result = f"Failed to check {username}"
                print(result)
                break

async def check_username_status(username):
    try:
        url = f"https://auth.roblox.com/v1/usernames/validate?birthday=2006-09-21T07:00:00.000Z&context=Signup&username={username}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                data = await response.json()
                if data["code"] == 0:
                    return "Valid", "🟢"
                elif data["code"] == 1:
                    return "Username Taken/Blocked", ""
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
    with open(file_path, 'r') as file:
        return [line.strip() for line in file if line.strip()]

def send_discord_webhook(url, username, status, emoji):
    data = {
        "embeds": [
            {
                "title": "New Hit:",
                "description": f"An unclaimed account was found: ```{username}```",
                "fields": [
                    {
                        "name": "Status",
                        "value": f"{status} {emoji}",
                        "inline": True
                    }
                ],
                "thumbnail": {
                    "url": "https://cdn.discordapp.com/avatars/697365002859970570/a75f2272195f77aecb0577c41eb56d9f.webp?size=4096"
                },
                "color": 0x00ff00 if status == "Valid" else 0xff0000 if status == "Inappropriate" else 0x808080
            }
        ]
    }
    headers = { "Content-Type": "application/json" }
    response = requests.post(url, json=data, headers=headers)

    if response.status_code == 204:
        print("Message sent successfully to Discord webhook!")
    else:
        print(f"Failed to send message. Status code: {response.status_code}")

async def main():
    usernames = load_usernames_from_file('usernames.txt')
    batch_size = 26
    wait_time = 5
    account_count = 0

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