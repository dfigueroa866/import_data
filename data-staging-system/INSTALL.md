# Installation Guide - Data Staging System

## 🚀 Quick Install

### Option 1: Using Make (Recommended)
```bash
make setup
```

### Option 2: Using Python Script
```bash
python install.py
```

### Option 3: Manual Installation
```bash
# Install dependencies
pip3 install -r requirements.txt

# Install package
pip3 install -e .

# Create environment file
cp .env.example .env
```

## 🔧 Platform-Specific Instructions

### macOS
```bash
# Install Homebrew if not installed
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install Python
brew install python

# Install the system
make install-mac
```

### Ubuntu/Debian
```bash
# Update system
sudo apt update

# Install Python and pip
sudo apt install -y python3 python3-pip

# Install the system
make install-ubuntu
```

### Windows
```bash
# Install Python from python.org
# Then run:
pip install -r requirements.txt
pip install -e .
```

## 🐛 Troubleshooting

### Issue: "pip: No such file or directory"
**Solution:**
```bash
# Try these alternatives:
python3 -m pip install -r requirements.txt
python -m pip install -r requirements.txt

# Or install pip:
# macOS: brew install python
# Ubuntu: sudo apt install python3-pip
```

### Issue: "Permission denied"
**Solution:**
```bash
# Use user installation:
pip3 install --user -r requirements.txt
pip3 install --user -e .
```

### Issue: "Module not found"
**Solution:**
```bash
# Check Python path:
python3 -c "import sys; print(sys.path)"

# Reinstall in development mode:
pip3 install -e .
```

## ✅ Verify Installation

```bash
# Check dependencies
make check-deps

# Test import
python3 -c "import data_staging; print('✅ Success')"

# Run tests
make test-run
```

## 🚀 Start the System

```bash
# Start API server
make run

# Start dashboard (in another terminal)
make dashboard
```

## 📍 Access Points

- **API**: http://localhost:8000
- **Docs**: http://localhost:8000/docs  
- **Dashboard**: http://localhost:8501
- **Health**: http://localhost:8000/health