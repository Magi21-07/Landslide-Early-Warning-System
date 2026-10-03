import ast
import os
import sys
import importlib.util

def get_all_python_files(directories):
    py_files = []
    for d in directories:
        for root, _, files in os.walk(d):
            for f in files:
                if f.endswith('.py'):
                    py_files.append(os.path.join(root, f))
    return py_files

def extract_imports(filepath):
    imports = set()
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read(), filename=filepath)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for name in node.names:
                    imports.add(name.name.split('.')[0])
            elif isinstance(node, ast.ImportFrom):
                if node.level == 0 and node.module:
                    imports.add(node.module.split('.')[0])
    except Exception as e:
        print(f"Failed to parse {filepath}: {e}")
    return imports

def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src_dir = os.path.join(base_dir, 'src')
    scripts_dir = os.path.join(base_dir, 'scripts')
    
    dirs_to_scan = []
    if os.path.exists(src_dir): dirs_to_scan.append(src_dir)
    if os.path.exists(scripts_dir): dirs_to_scan.append(scripts_dir)
    
    py_files = get_all_python_files(dirs_to_scan)
    all_imports = set()
    for pf in py_files:
        all_imports.update(extract_imports(pf))
        
    # Standard library in Python 3.10+
    try:
        stdlib = set(sys.stdlib_module_names)
    except AttributeError:
        # Fallback empty if older than 3.10
        stdlib = set()
        
    local_modules = {'src', 'scripts', 'tests', 'model', 'api', 'features', 'etl', 'risk'}
    
    third_party = all_imports - stdlib - local_modules
    
    # Filter out known standard libs that might be missed
    stdlib_extra = {'os', 'sys', 'ast', 'datetime', 'logging', 'concurrent', 'math', 'typing', 'time', 'functools', 'importlib', 'json', 'sqlite3'}
    third_party = third_party - stdlib_extra
    
    # Try importing to see if installed
    missing = []
    for pkg in third_party:
        if not importlib.util.find_spec(pkg):
            missing.append(pkg)
            
    # Some packages have different import name vs pip name (e.g. sklearn -> scikit-learn, ee -> earthengine-api)
    mapping = {
        'sklearn': 'scikit-learn',
        'ee': 'earthengine-api',
        'shap': 'shap',
        'httpx': 'httpx',
        'xgboost': 'xgboost',
        'pandas': 'pandas',
        'numpy': 'numpy',
        'joblib': 'joblib',
        'scipy': 'scipy',
        'pydantic': 'pydantic',
        'fastapi': 'fastapi',
        'uvicorn': 'uvicorn',
        'rasterio': 'rasterio',
        'geopandas': 'geopandas',
        'dotenv': 'python-dotenv'
    }
    
    pip_packages = [mapping.get(m, m) for m in missing]
    print("MISSING_PACKAGES=" + ",".join(pip_packages))
    print("ALL_THIRD_PARTY=" + ",".join(third_party))

if __name__ == "__main__":
    main()
