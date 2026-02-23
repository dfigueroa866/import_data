"""Check Python dependencies script"""
import importlib

def check_dependencies():
    """Check if required Python packages are installed"""
    
    core_packages = ['fastapi', 'sqlalchemy', 'pydantic', 'uvicorn', 'streamlit', 'pandas']
    optional_packages = ['psycopg2', 'plotly', 'requests', 'dotenv', 'supabase']
    
    missing_core = []
    missing_optional = []
    
    print("Checking core dependencies:")
    for package in core_packages:
        package_name = package.replace('-', '_')
        try:
            importlib.import_module(package_name)
            print(f'✅ {package}')
        except ImportError:
            print(f'❌ {package}')
            missing_core.append(package)
    
    print("\nChecking optional dependencies:")
    for package in optional_packages:
        package_name = package.replace('-', '_')
        try:
            importlib.import_module(package_name)
            print(f'✅ {package}')
        except ImportError:
            print(f'⚠️  {package} (optional)')
            missing_optional.append(package)
    
    print("\n" + "="*40)
    if missing_core:
        print(f'❌ Missing core packages: {", ".join(missing_core)}')
        print('🔧 Run: make install-deps')
        return False
    else:
        print('✅ All core dependencies installed!')
        
    if missing_optional:
        print(f'⚠️  Optional packages missing: {", ".join(missing_optional)}')
    
    return True

if __name__ == '__main__':
    check_dependencies()


# Make it executable
#chmod +x scripts/setup/check_dependencies.py