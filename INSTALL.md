# PesoRate Withdrawal Tracker — Install Instructions

This guide walks you through installing the tracker from GitHub and running
it on your own laptop. Follow the section that matches your operating system.

Repo: https://github.com/darrenodell/PesoRate

---

## macOS

### 1. Install Python 3.12

- Go to https://www.python.org/downloads/macos/
- Under **Python 3.12**, download the **macOS 64-bit universal2 installer**
  (a `.pkg` file).
- Open the downloaded file and follow the installer prompts (click through
  the defaults; enter your Mac password when asked).

### 2. Download the app from GitHub

- Open https://github.com/darrenodell/PesoRate in a web browser.
- Click the green **Code** button, then **Download ZIP**.
- Move the downloaded `PesoRate-main.zip` to your **Desktop**.
- Double-click the ZIP to unzip it. You should now have a folder called
  `PesoRate-main` on your Desktop.

### 3. Open Terminal

- Press **Cmd + Space**, type `Terminal`, press **Enter**.

### 4. Go to the app folder

Copy and paste this into Terminal, then press Enter:

```
cd ~/Desktop/PesoRate-main/withdrawal_tracker
```

### 5. Install the app's Python packages

```
python3.12 -m pip install -r requirements.txt
```

This will download a bunch of things — that's normal. It takes a minute or two.

### 6. Run the app

```
python3.12 -m streamlit run app.py
```

Your web browser will automatically open to `http://localhost:8501` with the
tracker.

### 7. Stopping and restarting

- To stop the app: click on Terminal and press **Ctrl + C**.
- To start it again later: reopen Terminal and repeat **steps 4 and 6**.

---

## Windows

### 1. Install Python 3.12

- Go to https://www.python.org/downloads/windows/
- Under **Python 3.12**, download the **Windows installer (64-bit)** (a `.exe` file).
- Run the installer. **Very important:** on the first screen, check the box
  that says **"Add python.exe to PATH"** before clicking **Install Now**.

### 2. Download the app from GitHub

- Open https://github.com/darrenodell/PesoRate in a web browser.
- Click the green **Code** button, then **Download ZIP**.
- Move the downloaded `PesoRate-main.zip` to your **Desktop**.
- Right-click the ZIP and choose **Extract All…** → point it at your Desktop
  and click **Extract**. You should now have a folder called `PesoRate-main`
  on your Desktop.

### 3. Open Command Prompt

- Press the **Windows key**, type `cmd`, press **Enter**.

### 4. Go to the app folder

Copy and paste this into Command Prompt, then press Enter:

```
cd %USERPROFILE%\Desktop\PesoRate-main\withdrawal_tracker
```

### 5. Install the app's Python packages

```
py -3.12 -m pip install -r requirements.txt
```

This will download a bunch of things — that's normal. It takes a minute or two.

### 6. Run the app

```
py -3.12 -m streamlit run app.py
```

Your web browser will automatically open to `http://localhost:8501` with the
tracker.

### 7. Stopping and restarting

- To stop the app: click on Command Prompt and press **Ctrl + C**.
- To start it again later: reopen Command Prompt and repeat **steps 4 and 6**.

---

## Troubleshooting

- **"command not found" or "not recognized"** after installing Python:
  close the Terminal / Command Prompt window and open a new one. The new
  window will pick up the updated PATH.
- **`pip install` fails with a permissions error**: add `--user` at the end
  of the install command, e.g.
  `python3.12 -m pip install --user -r requirements.txt`.
- **Browser doesn't open automatically**: manually visit
  http://localhost:8501 in any browser.
- **Anything else**: message Darren with a screenshot of the error.

---

## About your data

Your transactions are stored in a `data/` folder inside `withdrawal_tracker`.
Nothing is uploaded anywhere — it stays on your laptop.
