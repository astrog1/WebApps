# Cloudflare Tunnel Setup (Windows 11, Beginner Guide)

This guide lets you open your local apps to the internet with your own domain, without router port forwarding.

It is written for your current app setup:
- Home page hub: `http://localhost:8080`
- Yahtzee: `http://localhost:5102`
- Daily Math: `http://localhost:5103`

## What You Need

1. A domain name you own (for example `yourdomain.com`)
2. A Cloudflare account
3. This repo running on your Windows 11 PC

## 1) Put Your Domain on Cloudflare

1. Log in to Cloudflare.
2. Add your domain.
3. At your domain registrar (GoDaddy, Namecheap, etc.), change nameservers to the ones Cloudflare gives you.
4. Wait until Cloudflare shows the domain as active.

## 2) Install `cloudflared` on Windows 11

Open PowerShell and run:

```powershell
winget install --id Cloudflare.cloudflared
```

Verify install:

```powershell
cloudflared --version
```

## 3) Log In and Create a Tunnel

In PowerShell:

```powershell
cloudflared tunnel login
```

A browser tab opens. Pick your domain and approve.

Then create one tunnel:

```powershell
cloudflared tunnel create webapps-tunnel
```

Save the tunnel ID shown in output. You will use it below.

## 4) Create Tunnel Config File

Create this folder/file if it does not exist:

- Folder: `C:\Users\<YOUR_WINDOWS_USER>\.cloudflared`
- File: `C:\Users\<YOUR_WINDOWS_USER>\.cloudflared\config.yml`

Put this in `config.yml` (replace placeholders):

```yaml
tunnel: <YOUR_TUNNEL_ID>
credentials-file: "C:\\Users\\<YOUR_WINDOWS_USER>\\.cloudflared\\<YOUR_TUNNEL_ID>.json"

ingress:
  - hostname: home.yourdomain.com
    service: http://localhost:8080
  - hostname: yahtzee.yourdomain.com
    service: http://localhost:5102
  - hostname: math.yourdomain.com
    service: http://localhost:5103
  - service: http_status:404
```

## 5) Create DNS Records for Each Subdomain

Run:

```powershell
cloudflared tunnel route dns webapps-tunnel home.yourdomain.com
cloudflared tunnel route dns webapps-tunnel yahtzee.yourdomain.com
cloudflared tunnel route dns webapps-tunnel math.yourdomain.com
```

## 6) Start Your Local Apps

From this repo:

```powershell
cd C:\Users\natfo\Desktop\hosting_apps
.\start_local.ps1 start
```

## 7) Start the Tunnel

In another PowerShell window:

```powershell
cloudflared tunnel run webapps-tunnel
```

Now test:
- `https://home.yourdomain.com`
- `https://yahtzee.yourdomain.com`
- `https://math.yourdomain.com`

## Optional: Auto-Start Tunnel on Boot

Run PowerShell as Administrator:

```powershell
cloudflared service install
```

This installs `cloudflared` as a Windows service.

Notes:
- Service auto-starts the tunnel.
- It does not auto-start your Python apps. You still need `.\start_local.ps1 start` after reboot, unless you add your own startup task.

## Troubleshooting

- `502 Bad Gateway`
  - The target app is not running locally.
  - Run `.\start_local.ps1 status`.

- Domain not loading yet
  - DNS may still be propagating.
  - Wait a few minutes and test again.

- Daily Math says API key is missing
  - Set it once:
  - `setx OPENAI_API_KEY "sk-..."`
  - Open a new PowerShell window, then restart services:
  - `.\start_local.ps1 restart`

- Tunnel looks connected but wrong app opens
  - Check `config.yml` hostnames and ports carefully.

## Security Tip

Anything you expose with a public domain can be reached from the internet.
If you want login protection in front of these apps, add Cloudflare Access policies later.
