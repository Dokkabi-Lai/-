# WLB大作战 - 部署指南

> 推荐使用新的 [Render + Supabase 部署指南](DEPLOY_RENDER.md)。下面的 Koyeb、Railway 与本地服务器内容仅作备选，免费额度可能随平台政策变化。

## 方式零：Koyeb 免费部署（国内可访问，无需信用卡）

Koyeb 提供永久免费实例（1个 Web 服务 + 1GB PostgreSQL 数据库），国内可直接访问。

### 步骤

1. **安装 Koyeb CLI**
```bash
curl -L "https://github.com/koyeb/koyeb-cli/releases/latest/download/koyeb_linux_amd64" -o koyeb
chmod +x koyeb
sudo mv koyeb /usr/local/bin/
```

2. **登录 Koyeb**
```bash
koyeb login
# 会打开浏览器，用 GitHub 账号登录即可，无需信用卡
```

3. **部署应用**
```bash
cd /Users/laishuhuan/Desktop/求职软件
koyeb init --config koyeb.yml
koyeb deploy
```

4. **配置环境变量**
- 在 Koyeb 控制台找到你的应用
- Environment Variables 添加：
  - `LLM_API_KEY` = 你的 DeepSeek API Key
  - `POSTGRES_PASSWORD` = 设置一个数据库密码（自定义）

5. **访问应用**
- 部署完成后会获得一个公网域名，如 `https://xxx.koyeb.app`
- 分享给别人即可使用

### 注意事项
- 免费版：1 个 Web 服务 + 1GB PostgreSQL
- 不支持持久化卷（但用 PostgreSQL 数据库代替，数据不会丢）
- 无信用卡要求
- 国内访问速度一般，但可用

---

## 方式一：Railway 免费部署（需翻墙）

Railway 提供每月 $1 免费额度 + 0.5GB 持久化存储，足够个人使用。

### 步骤

1. **把代码推到 GitHub**
```bash
cd /Users/laishuhuan/Desktop/求职软件
git init && git add -A && git commit -m "init"
# 在 GitHub 创建一个仓库，然后：
git remote add origin https://github.com/你的用户名/wlb.git
git push -u origin main
```

2. **在 Railway 部署**
- 打开 https://railway.app ，用 GitHub 登录
- 点 **New Project** → **Deploy from GitHub repo** → 选你的仓库
- Railway 会自动识别 `railway.json` 和 `Dockerfile`，开始构建

3. **添加持久化存储（重要！）**
- 在服务设置里点 **Volumes** → **Add Volume**
- 挂载路径填：`/app/data`
- 这样 SQLite 数据库和上传的简历不会丢失

4. **配置环境变量**
- 在服务的 **Variables** 标签里添加：
  - `LLM_API_KEY` = 你的 DeepSeek API Key（可选，也可直接写在 config.yaml 里）

5. **生成公网链接**
- 在 **Settings** → **Networking** → 点 **Generate Domain**
- 会得到一个 `https://wlb-production.up.railway.app` 这样的链接
- 分享给别人即可，注册登录后数据各自独立

### 注意事项
- 免费额度约够一个小项目跑一整月，如果用超了服务会暂停
- 首次构建较慢（装 Playwright），后续部署会快
- 如果流量大或需要更多资源，升级 Hobby 计划 $5/月

---

## 方式一：自有云服务器 Docker 部署

### 前置要求
- 一台云服务器（阿里云/腾讯云/华为云等，2核2G即可）
- 服务器安全组/防火墙开放 8000 端口

### 步骤

```bash
# 1. 上传项目到服务器（二选一）
# 方式A：git clone
git clone <你的仓库地址> && cd 求职软件

# 方式B：scp 上传
scp -r /Users/laishuhuan/Desktop/求职软件 root@你的服务器IP:~/wlb
ssh root@你的服务器IP
cd ~/wlb

# 2. 配置
cp backend/config.yaml.example backend/config.yaml
vim backend/config.yaml  # 填入你的 DeepSeek API Key

# 3. 一键部署
bash deploy.sh
```

部署成功后访问 `http://服务器IP:8000` 即可使用。

### 常用命令

```bash
docker compose logs -f      # 查看日志
docker compose restart       # 重启
docker compose down          # 停止
docker compose up -d --build # 更新代码后重新部署
```

### 如果要换端口

```bash
PORT=80 docker compose up -d  # 用 80 端口（不用输端口号）
```

记得在云服务器安全组里开放对应端口。

---

## 方式二：直接部署（不用 Docker）

```bash
# 1. 安装 Python 3.11+
sudo apt update && sudo apt install -y python3.11 python3.11-venv python3-pip

# 2. 创建虚拟环境
cd backend
python3.11 -m venv venv
source venv/bin/activate

# 3. 安装依赖
pip install -r requirements.txt
playwright install chromium --with-deps

# 4. 配置
cp config.yaml.example config.yaml
vim config.yaml  # 填入 API Key

# 5. 启动
mkdir -p data/resumes logs
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 后台运行（使用 systemd）

```bash
sudo tee /etc/systemd/system/wlb.service << 'EOF'
[Unit]
Description=WLB大作战
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/wlb/backend
ExecStart=/root/wlb/backend/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable wlb
sudo systemctl start wlb

# 查看状态
sudo systemctl status wlb
# 查看日志
journalctl -u wlb -f
```

---

## 方式三：ngrok 临时分享（不需要服务器）

在本机运行：
```bash
brew install ngrok   # macOS
ngrok http 8000
```
会生成一个公网链接，发给别人即可访问。关机后失效。

---

## 绑定域名（可选）

如果你有域名，可以用 nginx 反向代理：

```bash
sudo apt install -y nginx

sudo tee /etc/nginx/sites-available/wlb << 'EOF'
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        client_max_body_size 20M;
    }
}
EOF

sudo ln -s /etc/nginx/sites-available/wlb /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

### HTTPS（免费证书）
```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```
