# ⚡ Quick Fix cho lỗi Selenium executable_path

## Vấn đề
```
TypeError: WebDriver.__init__() got an unexpected keyword argument 'executable_path'
```

## Giải pháp nhanh trên Server

### Bước 1: Cài đặt/cập nhật ChromeDriver vào PATH

```bash
# Tải ChromeDriver mới nhất
cd /tmp
CHROME_VERSION=$(google-chrome --version | awk '{print $3}' | cut -d. -f1)
CHROMEDRIVER_VERSION=$(curl -s "https://chromedriver.storage.googleapis.com/LATEST_RELEASE_${CHROME_VERSION}")
wget -O chromedriver.zip "https://chromedriver.storage.googleapis.com/${CHROMEDRIVER_VERSION}/chromedriver_linux64.zip"
unzip chromedriver.zip
sudo mv chromedriver /usr/local/bin/
sudo chmod +x /usr/local/bin/chromedriver

# Hoặc dùng Chrome for Testing (khuyến nghị cho Chrome mới)
# Download từ: https://googlechromelabs.github.io/chrome-for-testing/
```

### Bước 2: Đảm bảo chromedriver-linux trong project có quyền thực thi

```bash
cd /var/www/giadungplus
chmod +x chromedriver-linux

# Hoặc copy vào /usr/local/bin
sudo cp chromedriver-linux /usr/local/bin/chromedriver
sudo chmod +x /usr/local/bin/chromedriver
```

### Bước 3: Test ChromeDriver

```bash
/usr/local/bin/chromedriver --version
# Hoặc
chromedriver --version
```

### Bước 4: Pull code mới và restart

```bash
cd /var/www/giadungplus
git pull origin main
sudo supervisorctl restart giadungplus
```

---

## Hoặc: Downgrade Selenium về version cũ hơn (tạm thời)

Nếu vẫn không hoạt động, có thể downgrade Selenium:

```bash
cd /var/www/giadungplus
source venv/bin/activate
pip install "selenium<4.6.0" "selenium-wire"
sudo supervisorctl restart giadungplus
```

**Lưu ý:** Cách này không khuyến nghị, nhưng có thể dùng tạm thời.

