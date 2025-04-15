#!/bin/bash

# --- CẤU HÌNH ---
APP_DIR="/home/apidownload"
APP_FILE="app.py"
APP_URL="https://raw.githubusercontent.com/tocongtruong/apidownload/refs/heads/main/app.py"

SERVICE_NAME="apidownload"

read -p "🔹 Nhập domain bạn muốn dùng (ví dụ: api.domain.com): " DOMAIN

# Lấy IP VPS
SERVER_IP=$(curl -s ifconfig.me)
DOMAIN_IP=$(dig +short "$DOMAIN" | grep -Eo '([0-9]{1,3}\.){3}[0-9]{1,3}' | head -n 1)

echo "🔍 Kiểm tra domain $DOMAIN có trỏ về IP VPS ($SERVER_IP)..."
if [ "$DOMAIN_IP" != "$SERVER_IP" ]; then
    echo "❌ Domain chưa trỏ đúng IP VPS. IP hiện tại: $DOMAIN_IP"
    exit 1
fi

echo "✅ Domain hợp lệ. Bắt đầu cài đặt..."

# Cài gói cần thiết
apt update
apt upgrade
apt install -y curl python3 python3-pip python3-venv nginx certbot python3-certbot-nginx

# Tạo thư mục app
mkdir -p $APP_DIR

# Tải app.py từ GitHub
echo "📥 Đang tải app.py từ $APP_URL..."
curl -sL "$APP_URL" -o "$APP_DIR/$APP_FILE"

# Tạo virtualenv & cài requirements
cd "$APP_DIR"
python3 -m venv venv
source venv/bin/activate

cat <<EOF > requirements.txt
Flask==3.0.3
gdown==5.2.0
yt-dlp==2024.10.22
requests==2.32.3
certifi==2024.8.30
urllib3==2.2.3
EOF

pip install --upgrade pip
pip install -r requirements.txt

# Tạo systemd service
echo "⚙️ Tạo systemd service $SERVICE_NAME"
cat <<EOF > /etc/systemd/system/${SERVICE_NAME}.service
[Unit]
Description=Flask Downloader Service
After=network.target

[Service]
User=root
WorkingDirectory=$APP_DIR
Environment="PATH=$APP_DIR/venv/bin"
ExecStart=$APP_DIR/venv/bin/python $APP_FILE
Restart=always

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reexec
systemctl daemon-reload
systemctl enable $SERVICE_NAME
systemctl restart $SERVICE_NAME

# Cấu hình nginx
echo "🌐 Tạo cấu hình nginx cho $DOMAIN"
cat <<EOF > /etc/nginx/sites-available/$DOMAIN
server {
    listen 80;
    server_name $DOMAIN;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
    }
}
EOF

ln -sf /etc/nginx/sites-available/$DOMAIN /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx

# SSL certbot
echo "🔐 Cấp chứng chỉ SSL Let's Encrypt"
certbot --nginx -d $DOMAIN --non-interactive --agree-tos -m admin@$DOMAIN

# Thiết lập tự động gia hạn SSL bằng cron
echo "🔁 Đảm bảo cron job tự động gia hạn SSL tồn tại..."
CRON_JOB="0 3 * * * certbot renew --quiet --deploy-hook \"systemctl reload nginx\""

# Chỉ thêm nếu chưa có
if ! crontab -l 2>/dev/null | grep -Fq "certbot renew"; then
    (crontab -l 2>/dev/null; echo "$CRON_JOB") | crontab -
    echo "✅ Đã thêm cron job tự động gia hạn SSL vào crontab"
else
    echo "✅ Cron job đã tồn tại, không cần thêm lại"
fi

echo ""
echo "✅ Hoàn tất! API Flask đang chạy tại: https://$DOMAIN"
