import discord
from discord.ext import commands
from discord_webhook import DiscordWebhook
import requests
from pymongo import MongoClient
import os

# Load environmental variables
BOT_TOKEN = os.getenv('TOKEN')  # Replace with your Discord bot token
MONGODB_URI = os.getenv('MONGODB')  # Replace with your MongoDB connection URI
SITE24X7_API_KEY = os.getenv('API')  # Replace with your Site24x7 API key
DISCORD_WEBHOOK_URL = os.getenv('WEBHOOK')  # Replace with your Discord webhook URL

# MongoDB setup
client = MongoClient(MONGODB_URI)
db = client['your_database_name']  # Replace with your database name
monitors_collection = db['monitors']

# Enable intents
intents = discord.Intents.default()
intents.all()

# Default prefix is '!'
prefix = os.getenv('PREFIX')  # If 'BOT_PREFIX' is not set, default to '!'
bot = commands.Bot(command_prefix=prefix, intents=intents)

# User monitors dictionary to store user-specific monitor details
user_monitors = {}

bot.remove_command('help')

# Set up embed colors
EMBED_COLOR_SUCCESS = int(os.getenv('EMBED_COLOR_SUCCESS', '0x00ff00'), 16)
EMBED_COLOR_ERROR = int(os.getenv('EMBED_COLOR_ERROR', '0xff0000'), 16)

def log_to_webhook(embed):
    webhook = DiscordWebhook(url=DISCORD_WEBHOOK_URL, embeds=[embed.to_dict()])
    webhook.execute()

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name} ({bot.user.id})')
    print('------')

@bot.command()
async def createmon(ctx, desired_monitor=None, monitor_name=None):
    if desired_monitor is None or monitor_name is None:
        embed = discord.Embed(title="Error", description=f"Correct usage: {prefix}createmon {{desired_monitor}} {{monitor_name}}", color=EMBED_COLOR_ERROR)
        await ctx.send(embed=embed)
        return

    # Check if the provided project starts with "https://"
    if not desired_monitor.startswith("https://"):
        desired_monitor = f"https://{desired_monitor}"

    # Create Site24x7 monitor
    endpoint = "https://www.site24x7.com/api/current/monitors"
    headers = {
        "Authorization": f"Zoho-authtoken {SITE24X7_API_KEY}"
    }
    payload = {
        "monitorFriendlyName": monitor_name,
        "monitorURL": desired_monitor,
        "monitorType": "HTTP"
    }

    try:
        response = requests.post(endpoint, headers=headers, data=payload)
        response.raise_for_status()  # Raise an HTTPError for bad responses (4xx and 5xx)

        data = response.json()

        user_id = ctx.author.id
        server_id = ctx.guild.id
        server_invite = await ctx.channel.create_invite()

        if 'data' in data:
            monitor_id = data['data']['monitorId']
            user_monitors[user_id] = monitor_id

            # Save monitor details to MongoDB
            monitors_collection.insert_one({
                'user_id': user_id,
                'username': ctx.author.name,
                'server_id': server_id,
                'server_invite': str(server_invite),
                'monitor_id': monitor_id,
                'monitor_name': monitor_name,
                'response': 'success',
            })

            # Send success message to the channel
            embed = discord.Embed(title="Monitor Created", color=EMBED_COLOR_SUCCESS)
            embed.add_field(name="Monitor ID", value=monitor_id, inline=False)
            embed.add_field(name="Success Message", value="Monitor created successfully!", inline=False)
            log_to_webhook(embed)
            await ctx.send(embed=embed)
        else:
            # Save monitor details to MongoDB
            monitors_collection.insert_one({
                'user_id': user_id,
                'username': ctx.author.name,
                'server_id': server_id,
                'server_invite': str(server_invite),
                'monitor_name': monitor_name,
                'response': f'fail: {response.status_code} - {data.get("message", "Unknown error")}',
            })

            embed = discord.Embed(title="Error", description=f"Failed to create monitor. {data.get('message', 'Unknown error')}", color=EMBED_COLOR_ERROR)
            log_to_webhook(embed)
            await ctx.send(embed=embed)

    except requests.exceptions.HTTPError as http_err:
        # Handle HTTP errors (4xx and 5xx)
        embed = discord.Embed(title="HTTP Error", description=f"HTTP error occurred: {http_err}", color=EMBED_COLOR_ERROR)
        log_to_webhook(embed)
        await ctx.send(embed=embed)

    except requests.exceptions.RequestException as req_err:
        # Handle other request-related errors
        embed = discord.Embed(title="Request Error", description=f"Request error occurred: {req_err}", color=EMBED_COLOR_ERROR)
        log_to_webhook(embed)
        await ctx.send(embed=embed)

@bot.command()
async def removemon(ctx, monitor_name_or_id=None):
    user_id = ctx.author.id

    if monitor_name_or_id is None or user_id not in user_monitors:
        embed = discord.Embed(title="Error", description=f"Correct usage: {prefix}removemon {{monitor_name_or_id}}", color=EMBED_COLOR_ERROR)
        await ctx.send(embed=embed)
        return

    monitor_id = user_monitors[user_id]

    # Remove Site24x7 monitor
    endpoint = f"https://www.site24x7.com/api/current/monitors/{monitor_id}"
    headers = {
        "Authorization": f"Zoho-authtoken {SITE24X7_API_KEY}"
    }

    try:
        response = requests.delete(endpoint, headers=headers)
        response.raise_for_status()  # Raise an HTTPError for bad responses (4xx and 5xx)

        data = response.json()

        server_id = ctx.guild.id
        server_invite = await ctx.channel.create_invite()

        if 'data' in data and data['data'] == 'Monitor deleted successfully':
            # Remove monitor details from the dictionary
            del user_monitors[user_id]

            # Remove monitor details from MongoDB
            monitors_collection.delete_one({'user_id': user_id, 'monitor_id': monitor_id})

            # Send success message to the channel
            embed = discord.Embed(title="Monitor Removed", color=EMBED_COLOR_SUCCESS)
            embed.add_field(name="Monitor ID", value=monitor_id, inline=False)
            embed.add_field(name="Success Message", value="Monitor removed successfully!", inline=False)
            log_to_webhook(embed)
            await ctx.send(embed=embed)
        else:
            embed = discord.Embed(title="Error", description=f"Failed to remove monitor. {data.get('message', 'Unknown error')}", color=EMBED_COLOR_ERROR)
            log_to_webhook(embed)
            await ctx.send(embed=embed)

    except requests.exceptions.HTTPError as http_err:
        # Handle HTTP errors (4xx and 5xx)
        embed = discord.Embed(title="HTTP Error", description=f"HTTP error occurred: {http_err}", color=EMBED_COLOR_ERROR)
        log_to_webhook(embed)
        await ctx.send(embed=embed)

    except requests.exceptions.RequestException as req_err:
        # Handle other request-related errors
        embed = discord.Embed(title="Request Error", description=f"Request error occurred: {req_err}", color=EMBED_COLOR_ERROR)
        log_to_webhook(embed)
        await ctx.send(embed=embed)

@bot.command()
async def status(ctx, monitor_name_or_id=None):
    user_id = ctx.author.id

    if monitor_name_or_id is None or user_id not in user_monitors:
        embed = discord.Embed(title="Error", description=f"Correct usage: {prefix}status {{monitor_name_or_id}}", color=EMBED_COLOR_ERROR)
        await ctx.send(embed=embed)
        return

    monitor_id = user_monitors[user_id]

    # Get Site24x7 monitor details
    endpoint = f"https://www.site24x7.com/api/current/monitors/{monitor_id}"
    headers = {
        "Authorization": f"Zoho-authtoken {SITE24X7_API_KEY}"
    }

    try:
        response = requests.get(endpoint, headers=headers)
        response.raise_for_status()  # Raise an HTTPError for bad responses (4xx and 5xx)

        data = response.json()

        if 'data' in data:
            # Get monitor details
            monitor_name = data['data']['monitorFriendlyName']
            monitor_url = data['data']['monitorURL']
            monitor_status = data['data']['monitorStatus']
            monitor_type = data['data']['monitorType']

            # Send monitor details in an embed message
            embed = discord.Embed(title=f"Monitor Details - {monitor_name}", color=EMBED_COLOR_SUCCESS)
            embed.add_field(name="Monitor ID", value=monitor_id, inline=False)
            embed.add_field(name="Monitor Name", value=monitor_name, inline=False)
            embed.add_field(name="Monitor URL", value=monitor_url, inline=False)
            embed.add_field(name="Monitor Status", value=monitor_status, inline=False)
            embed.add_field(name="Monitor Type", value=monitor_type, inline=False)
            log_to_webhook(embed)
            await ctx.send(embed=embed)
        else:
            embed = discord.Embed(title="Error", description=f"Failed to retrieve monitor details. {data.get('message', 'Unknown error')}", color=EMBED_COLOR_ERROR)
            log_to_webhook(embed)
            await ctx.send(embed=embed)

    except requests.exceptions.HTTPError as http_err:
        # Handle HTTP errors (4xx and 5xx)
        embed = discord.Embed(title="HTTP Error", description=f"HTTP error occurred: {http_err}", color=EMBED_COLOR_ERROR)
        log_to_webhook(embed)
        await ctx.send(embed=embed)

    except requests.exceptions.RequestException as req_err:
        # Handle other request-related errors
        embed = discord.Embed(title="Request Error", description=f"Request error occurred: {req_err}", color=EMBED_COLOR_ERROR)
        log_to_webhook(embed)
        await ctx.send(embed=embed)

@bot.command()
async def search(ctx, search_id=None):
    if search_id is None:
        embed = discord.Embed(title="Error", description=f"Correct usage: {prefix}search {{search_id}}", color=EMBED_COLOR_ERROR)
        await ctx.send(embed=embed)
        return

    # Get monitor details from MongoDB
    result = monitors_collection.find_one({'monitor_id': search_id})

    if result:
        # Send monitor details in an embed message
        embed = discord.Embed(title=f"Search Result - {result['monitor_name']}", color=EMBED_COLOR_SUCCESS)
        embed.add_field(name="User ID", value=result['user_id'], inline=False)
        embed.add_field(name="Username", value=result['username'], inline=False)
        embed.add_field(name="Server ID", value=result['server_id'], inline=False)
        embed.add_field(name="Server Invite", value=result['server_invite'], inline=False)
        embed.add_field(name="Monitor ID", value=result['monitor_id'], inline=False)
        embed.add_field(name="Monitor Name", value=result['monitor_name'], inline=False)
        embed.add_field(name="Response", value=result['response'], inline=False)
        log_to_webhook(embed)
        await ctx.send(embed=embed)
    else:
        embed = discord.Embed(title="Error", description=f"No monitor found with ID {search_id}", color=EMBED_COLOR_ERROR)
        log_to_webhook(embed)
        await ctx.send(embed=embed)

@bot.command()
async def help(ctx):
    # Display help message with dynamic prefix
    embed = discord.Embed(title="Bot Commands", color=EMBED_COLOR_SUCCESS)
    embed.add_field(name=f"{prefix}createmon {{desired_monitor}} {{monitor_name}}", value="Create a new monitor", inline=False)
    embed.add_field(name=f"{prefix}removemon {{monitor_name_or_id}}", value="Remove an existing monitor", inline=False)
    embed.add_field(name=f"{prefix}status {{monitor_name_or_id}}", value="Get details of a monitor", inline=False)
    embed.add_field(name=f"{prefix}search {{search_id}}", value="Search for a monitor in the database", inline=False)
    log_to_webhook(embed)
    await ctx.send(embed=embed)

bot.run(BOT_TOKEN)
