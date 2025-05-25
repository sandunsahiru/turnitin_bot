#!/bin/bash

# Deployment script for Turnitin Bot on Digital Ocean
# Run this script on your droplet to set up or update the bot

set -e  # Exit on any error

echo "🚀 Starting Turnitin Bot deployment..."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    print_error "Please run this script as root"
    exit 1
fi

# Update system packages
print_status "Updating system packages..."
apt update && apt upgrade -y

# Install required system packages
print_status "Installing required system packages..."
apt install -y python3 python3-pip python3-venv git curl wget

# Install Playwright dependencies
print_status "Installing Playwright browser dependencies..."
apt install -y \
    libnss3 \
    libatk-bridge2.0-0 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libgbm1 \
    libxss1 \
    libasound2 \
    libatspi2.0-0 \
    libgtk-3-0

# Set up working directory
WORK_DIR="/root/turnitin_bot"
print_status "Setting up working directory: $WORK_DIR"

# Create directory if it doesn't exist
mkdir -p $WORK_DIR
cd $WORK_DIR

# Clone or update repository
if [ -d ".git" ]; then
    print_status "Updating existing repository..."
    git stash  # Stash any local changes
    git pull origin main
    git stash pop 2>/dev/null || true  # Apply stashed changes if any
else
    print_status "Cloning repository..."
    git clone https://github.com/sandunsahiru/turnitin_bot.git .
fi

# Set up Python virtual environment
print_status "Setting up Python virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

# Activate virtual environment and install requirements
print_status "Installing Python dependencies..."
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install requirements
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
else
    # Install essential packages
    pip install python-dotenv telebot playwright
fi

# Install Playwright browsers
print_status "Installing Playwright browsers..."
playwright install chromium
playwright install firefox

# Set up environment file if it doesn't exist
if [ ! -f ".env" ]; then
    print_warning "Creating .env file template..."
    cat > .env << 'EOF'
# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN=7817359683:AAFlDLzPqgT2t232-XtaCFQ6EQDhgouwY40
ADMIN_TELEGRAM_ID=1004525688

# Turnitin Account Credentials
TURNITIN_EMAIL=alumosegonzo@gmail.com
TURNITIN_PASSWORD=WebCodoo@327134

EOF
    print_warning "Please edit .env file with your actual credentials:"
    print_warning "nano $WORK_DIR/.env"
fi

# Create systemd service file
print_status "Creating systemd service file..."
cat > /etc/systemd/system/turnitin_bot.service << 'EOF'
[Unit]
Description=Turnitin Bot Service
After=network.target
Wants=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/turnitin_bot
Environment=PATH=/root/turnitin_bot/venv/bin
ExecStart=/root/turnitin_bot/venv/bin/python /root/turnitin_bot/main.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=turnitin_bot

# Environment variables for headless operation
Environment=DISPLAY=:0
Environment=PLAYWRIGHT_BROWSERS_PATH=/root/.cache/ms-playwright

# Resource limits
LimitNOFILE=65536
MemoryLimit=2G

# Security settings
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=/root/turnitin_bot

[Install]
WantedBy=multi-user.target
EOF

# Create necessary directories
print_status "Creating necessary directories..."
mkdir -p uploads downloads

# Set proper permissions
chmod +x main.py
chmod 755 uploads downloads

# Reload systemd and enable the service
print_status "Configuring systemd service..."
systemctl daemon-reload
systemctl enable turnitin_bot

# Stop service if running
if systemctl is-active --quiet turnitin_bot; then
    print_status "Stopping existing service..."
    systemctl stop turnitin_bot
fi

# Start the service
print_status "Starting Turnitin Bot service..."
systemctl start turnitin_bot

# Check service status
sleep 3
if systemctl is-active --quiet turnitin_bot; then
    print_status "✅ Turnitin Bot service is running successfully!"
    print_status "Service status:"
    systemctl status turnitin_bot --no-pager -l
else
    print_error "❌ Failed to start Turnitin Bot service"
    print_error "Check logs with: journalctl -u turnitin_bot -f"
    exit 1
fi

# Display useful commands
print_status "📋 Useful commands:"
echo "  • Check status: systemctl status turnitin_bot"
echo "  • View logs: journalctl -u turnitin_bot -f"
echo "  • Stop service: systemctl stop turnitin_bot"
echo "  • Start service: systemctl start turnitin_bot"
echo "  • Restart service: systemctl restart turnitin_bot"
echo "  • Update bot: cd $WORK_DIR && bash deploy.sh"

print_status "🎉 Deployment completed successfully!"
print_warning "Don't forget to configure your .env file with the correct credentials!"

exit 0