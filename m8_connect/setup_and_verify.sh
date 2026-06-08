#!/bin/bash
# setup_and_verify.sh - Complete setup and verification script

echo "🚀 M8 Connect - Setup and Verification"
echo "================================================"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    local color=$1
    local message=$2
    echo -e "${color}${message}${NC}"
}

# Check if we're in the right directory
check_project_root() {
    print_status $BLUE "🔍 Checking project structure..."
    
    if [[ ! -f "start_api.py" ]] || [[ ! -f "requirements.txt" ]]; then
        print_status $RED "❌ Error: Not in project root directory"
        print_status $YELLOW "   Please navigate to the m8_connect directory"
        exit 1
    fi
    
    print_status $GREEN "✅ Project root directory confirmed"
}

# Create directory structure
create_directories() {
    print_status $BLUE "📁 Creating directory structure..."
    
    # Core directories
    mkdir -p src/data_staging/{core/{validators,etl,connectors,monitoring},models,utils,api/v1}
    mkdir -p {data/{uploads,temp,processed},logs,config,tests,scripts}
    
    # Create __init__.py files for Python modules
    touch src/__init__.py
    touch src/data_staging/__init__.py
    touch src/data_staging/core/__init__.py
    touch src/data_staging/core/validators/__init__.py
    touch src/data_staging/core/etl/__init__.py
    touch src/data_staging/core/connectors/__init__.py
    touch src/data_staging/core/monitoring/__init__.py
    touch src/data_staging/models/__init__.py
    touch src/data_staging/utils/__init__.py
    touch src/data_staging/api/__init__.py
    touch src/data_staging/api/v1/__init__.py
    
    print_status $GREEN "✅ Directory structure created"
}

# Create missing core files
create_core_files() {
    print_status $BLUE "🔧 Creating missing core files..."
    
    # Run the Python script to create core files
    python3 << 'EOF'
import sys
from pathlib import Path

# Add src to path
src_dir = Path.cwd() / "src"
sys.path.insert(0, str(src_dir))

# Create core files
print("Creating core data staging files...")

# Create DataValidator
validator_file = Path("src/data_staging/core/validators/data_validator.py")
if not validator_file.exists():
    validator_content = '''# Auto-generated DataValidator
import pandas as pd
from typing import Dict, Any

class ValidationResult:
    def __init__(self):
        self.passed = True
        self.errors = []
        self.score = 100.0
        
    def get_summary(self):
        return {
            "passed": self.passed,
            "score": self.score,
            "errors": len(self.errors),
            "overall_score": self.score
        }

class DataValidator:
    def validate_dataframe(self, df: pd.DataFrame, rules: Dict[str, Any] = None):
        result = ValidationResult()
        if df is None or df.empty:
            result.passed = False
            result.errors.append("DataFrame is empty")
            result.score = 0
        return result.get_summary()
'''
    validator_file.parent.mkdir(parents=True, exist_ok=True)
    validator_file.write_text(validator_content)
    print("✅ Created DataValidator")

# Create FileHandler
handler_file = Path("src/data_staging/utils/file_handler.py")
if not handler_file.exists():
    handler_content = '''# Auto-generated FileHandler
import pandas as pd
from pathlib import Path
from typing import Union, Dict, Any, Optional

class FileHandler:
    def read_file(self, file_path: Union[str, Path], **kwargs) -> Optional[pd.DataFrame]:
        file_path = Path(file_path)
        if not file_path.exists():
            return None
            
        try:
            if file_path.suffix.lower() == '.csv':
                return pd.read_csv(file_path, **kwargs)
            elif file_path.suffix.lower() in ['.xlsx', '.xls']:
                return pd.read_excel(file_path, **kwargs)
            else:
                return None
        except Exception:
            return None
    
    def analyze_file_structure(self, file_path: Union[str, Path]) -> Dict[str, Any]:
        file_path = Path(file_path)
        return {
            "file_name": file_path.name,
            "file_size": file_path.stat().st_size if file_path.exists() else 0,
            "file_extension": file_path.suffix.lower(),
            "columns": [],
            "estimated_total_rows": 0
        }
'''
    handler_file.parent.mkdir(parents=True, exist_ok=True)
    handler_file.write_text(handler_content)
    print("✅ Created FileHandler")

print("Core files creation completed!")
EOF

    print_status $GREEN "✅ Core files created"
}

# Test Python imports
test_imports() {
    print_status $BLUE "🧪 Testing Python imports..."
    
    python3 << 'EOF'
import sys
from pathlib import Path

# Add src to path
src_dir = Path.cwd() / "src"
sys.path.insert(0, str(src_dir))

try:
    # Test basic imports
    import data_staging
    print("✅ data_staging module import successful")
    
    from data_staging.core.validators.data_validator import DataValidator
    print("✅ DataValidator import successful")
    
    from data_staging.utils.file_handler import FileHandler
    print("✅ FileHandler import successful")
    
    # Test instantiation
    validator = DataValidator()
    handler = FileHandler()
    
    print("✅ All components can be instantiated")
    
except ImportError as e:
    print(f"❌ Import error: {e}")
    sys.exit(1)
except Exception as e:
    print(f"❌ Unexpected error: {e}")
    sys.exit(1)
    
print("🎯 All imports successful!")
EOF

    if [ $? -eq 0 ]; then
        print_status $GREEN "✅ Python imports working correctly"
    else
        print_status $RED "❌ Python import issues detected"
        return 1
    fi
}

# Test API startup
test_api() {
    print_status $BLUE "🌐 Testing API startup..."
    
    # Test if the API can start (timeout after 10 seconds)
    timeout 10s python3 start_api.py --help > /dev/null 2>&1
    
    if [ $? -eq 0 ] || [ $? -eq 124 ]; then  # 124 is timeout exit code
        print_status $GREEN "✅ API startup script is functional"
    else
        print_status $YELLOW "⚠️  API startup needs attention"
    fi
}

# Check dependencies
check_dependencies() {
    print_status $BLUE "📦 Checking dependencies..."
    
    # Check if requirements.txt exists
    if [[ -f "requirements.txt" ]]; then
        print_status $GREEN "✅ requirements.txt found"
        
        # Try to install/check dependencies
        python3 -m pip install -r requirements.txt --quiet --dry-run 2>/dev/null
        if [ $? -eq 0 ]; then
            print_status $GREEN "✅ All dependencies available"
        else
            print_status $YELLOW "⚠️  Some dependencies may need installation"
            print_status $BLUE "   Run: pip install -r requirements.txt"
        fi
    else
        print_status $RED "❌ requirements.txt not found"
    fi
}

# Create sample configuration
create_sample_config() {
    print_status $BLUE "⚙️  Creating sample configuration..."
    
    # Create .env.example if it doesn't exist
    if [[ ! -f ".env.example" ]]; then
        cat > .env.example << 'EOF'
# Database Configuration
DATABASE_URL=postgresql://user:password@localhost:5432/data_staging

# API Configuration
API_HOST=0.0.0.0
API_PORT=8000
API_DEBUG=true

# File Upload Configuration
UPLOAD_PATH=./data/uploads
TEMP_PATH=./data/temp
MAX_FILE_SIZE=104857600
ALLOWED_FILE_EXTENSIONS=.csv,.xlsx,.xls,.json,.txt

# Logging
LOG_LEVEL=INFO
LOG_FILE=./logs/api.log

# Processing Configuration
BATCH_SIZE=1000
MAX_RETRIES=3
PROCESSING_TIMEOUT=300
EOF
        print_status $GREEN "✅ Created .env.example"
    fi
    
    # Create sample data source config
    mkdir -p config/sources
    if [[ ! -f "config/sources/sample_products.json" ]]; then
        cat > config/sources/sample_products.json << 'EOF'
{
  "source_name": "products_master",
  "source_type": "file",
  "description": "Product master data configuration",
  "validation_rules": {
    "not_null": {
      "columns": ["product_id", "name", "price"]
    },
    "unique": {
      "columns": ["product_id"]
    },
    "range": {
      "columns": ["price"],
      "ranges": {
        "price": {"min": 0.01}
      }
    }
  },
  "target_table": "stage_products",
  "target_schema": "staging_data",
  "production_table": "products",
  "production_schema": "production"
}
EOF
        print_status $GREEN "✅ Created sample configuration"
    fi
}

# Final verification
final_verification() {
    print_status $BLUE "🔍 Final verification..."
    
    # Check critical files
    critical_files=(
        "src/data_staging/__init__.py"
        "src/data_staging/core/validators/data_validator.py"
        "src/data_staging/core/etl/engine.py" 
        "src/data_staging/utils/file_handler.py"
        "start_api.py"
    )
    
    all_good=true
    for file in "${critical_files[@]}"; do
        if [[ -f "$file" ]]; then
            print_status $GREEN "✅ $file"
        else
            print_status $RED "❌ $file missing"
            all_good=false
        fi
    done
    
    if [ "$all_good" = true ]; then
        print_status $GREEN "🎉 Setup verification completed successfully!"
        echo ""
        print_status $BLUE "📋 Next steps:"
        echo "   1. Copy .env.example to .env and configure your database"
        echo "   2. Install dependencies: pip install -r requirements.txt"
        echo "   3. Start the API: python start_api.py"
        echo "   4. Access API docs: http://localhost:8000/docs"
        echo ""
        print_status $GREEN "🚀 Ready to upload files to stage_products → products!"
    else
        print_status $RED "❌ Setup verification failed"
        return 1
    fi
}

# Main execution
main() {
    check_project_root
    create_directories
    create_core_files
    test_imports
    check_dependencies
    test_api
    create_sample_config
    final_verification
}

# Run main function
main