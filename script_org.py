# b-up.py (modified for web integration)

import os
import shutil
import re
from datetime import datetime
import filecmp
import hashlib

# Assume a global or passed-in logger/progress reporter
# For simplicity, we'll use a list to store messages for now.
# In a real app, this would be more sophisticated (e.g., WebSocket).
_progress_messages = []

def _log_progress(message):
    global _progress_messages
    _progress_messages.append(message)
    print(message) # Keep print for server-side console logging

def normalize_name(name):
    """Normalize names by treating hyphens and spaces as equivalent and removing special chars"""
    cleaned = re.sub(r'[^a-zA-Z0-9\s-]', '', name)
    return re.sub(r'[-_\s]', '', cleaned).strip().lower()

def normalize_filename(filename):
    """Normalize filenames by treating hyphens and spaces as equivalent before extension"""
    basename, ext = os.path.splitext(filename)
    normalized = re.sub(r'[-_\s]', '', basename).strip().lower()
    return f"{normalized}{ext.lower()}"

def normalize_category(category_name):
    """Normalize category names for case-insensitive comparison"""
    if not category_name:
        return None
    return category_name.strip().lower()

def are_categories_equivalent(cat1, cat2):
    """Check if two category names are equivalent (case-insensitive, JPEG=JPG)"""
    if not cat1 or not cat2:
        return False
    
    norm1 = normalize_category(cat1)
    norm2 = normalize_category(cat2)
    
    # Direct match
    if norm1 == norm2:
        return True
    
    # JPEG and JPG equivalence
    jpeg_variants = {'jpeg', 'jpg'}
    if norm1 in jpeg_variants and norm2 in jpeg_variants:
        return True
    
    return False

def is_variant_code(word):
    """Check if word is a variant code (single letter or number)"""
    return re.fullmatch(r'^[A-Za-z0-9]$', word)

def extract_name_code_variant(basename):
    """
    Improved extraction that properly handles technical filenames
    """
    cleaned = re.sub(r'[^\w\s\.-]', '', basename, flags=re.UNICODE)
    parts = re.split(r'[-_\s]', cleaned)
    parts = [p for p in parts if p]
    
    if not parts:
        return None, None, None
    
    _log_progress(f"DEBUG: Parsing '{basename}' -> parts: {parts}")
    
    name_parts = []
    code_parts = []
    variant = None
    
    if len(parts) > 1 and is_variant_code(parts[-1]):
        variant = parts[-1]
        parts = parts[:-1]
        _log_progress(f"DEBUG: Found variant: {variant}")
    
    version_pattern = r'\d+\.\d+'
    tech_with_version_idx = -1
    
    for i, part in enumerate(parts):
        if re.search(version_pattern, part):
            tech_with_version_idx = i
            _log_progress(f"DEBUG: Found technical term with version at index {i}: {part}")
            break
    
    if tech_with_version_idx != -1:
        if tech_with_version_idx == 0:
            name_parts = parts[:1]
            code_parts = parts[1:] if len(parts) > 1 else []
        else:
            name_parts = parts[:tech_with_version_idx]
            code_parts = parts[tech_with_version_idx:]
    else:
        if len(parts) == 1:
            single_part = parts[0]
            brand_model_match = re.match(r'^([a-zA-Z]+)(\d+.*)$', single_part)
            if brand_model_match:
                brand = brand_model_match.group(1)
                model = brand_model_match.group(2)
                name_parts = [brand]
                code_parts = [model]
                _log_progress(f"DEBUG: Split single part brand+model: brand='{brand}', model='{model}'")
            else:
                name_parts = [single_part]
                code_parts = []
                
        elif len(parts) == 2:
            first_part, second_part = parts[0], parts[1]
            
            brand_model_match = re.match(r'^([a-zA-Z]+)(\d+.*)$', first_part)
            if brand_model_match:
                brand = brand_model_match.group(1)
                model_part1 = brand_model_match.group(2)
                name_parts = [brand]
                code_parts = [model_part1, second_part]
                _log_progress(f"DEBUG: First part has brand+model: brand='{brand}', model='{model_part1}+{second_part}'")
            else:
                if re.fullmatch(r'[a-zA-Z]+', first_part) and re.search(r'\d', second_part):
                    name_parts = [first_part]
                    code_parts = [second_part]
                    _log_progress(f"DEBUG: Clear brand-model split: brand='{first_part}', model='{second_part}'")
                else:
                    if len(second_part) >= 2:
                        name_parts = [first_part]
                        code_parts = [second_part]
                    else:
                        name_parts = parts
                        code_parts = []
        else:
            first_part = parts[0]
            
            if re.fullmatch(r'[a-zA-Z]+', first_part):
                name_parts = [first_part]
                code_parts = parts[1:]
                _log_progress(f"DEBUG: Multi-part with alphabetic brand: brand='{first_part}', code='{parts[1:]}'")
            else:
                product_code_start = 1
                for i in range(1, len(parts)):
                    if re.search(r'\d', parts[i]):
                        product_code_start = i
                        break
                
                name_parts = parts[:product_code_start]
                code_parts = parts[product_code_start:]
    
    name = ' '.join(name_parts).strip() if name_parts else None
    
    if code_parts:
        if len(code_parts) > 1:
            code_portion = basename
            if name_parts:
                for name_part in name_parts:
                    code_portion = re.sub(rf'^{re.escape(name_part)}[-_\s]*', '', code_portion, 1)
            
            if variant:
                code_portion = re.sub(rf'[-_\s]*{re.escape(variant)}$', '', code_portion)
            
            if '_' in code_portion and '-' not in code_portion:
                code = '_'.join(code_parts)
            else:
                code = '-'.join(code_parts)
        else:
            code = code_parts[0]
    else:
        code = None
    
    if not name and code:
        if not re.search(r'\d', code) and len(code.split('-')) == 1:
            name = code.replace('-', ' ')
            code = None
    
    if not name and not code:
        name = ' '.join(parts[:1]) if parts else None
    
    _log_progress(f"DEBUG: Final result -> name: '{name}', code: '{code}', variant: '{variant}'")
    return name, code, variant

def get_file_category(filename):
    """Get file category with improved logic"""
    normalized = normalize_filename(filename)
    basename = os.path.basename(normalized)
    ext = os.path.splitext(normalized)[1].lower()
    
    if basename.startswith('img'):
        return 'Unedited'
    if ext in ['.webp']:
        return 'WEBP'
    if ext in ['.jpg', '.jpeg']:
        return 'JPEG'
    if ext in ['.mp4', '.mov', '.avi', '.mkv']:
        return 'Videos'
    return None

def find_existing_category_folder(parent_path, target_category):
    """Find existing category folder with case-insensitive and JPEG/JPG equivalence"""
    if not target_category:
        return None
        
    _log_progress(f"DEBUG: Looking for category folder '{target_category}' in '{parent_path}'")
    
    for item in os.listdir(parent_path):
        item_path = os.path.join(parent_path, item)
        if os.path.isdir(item_path):
            _log_progress(f"DEBUG: Checking folder '{item}' against category '{target_category}'")
            
            if are_categories_equivalent(item, target_category):
                _log_progress(f"DEBUG: Found matching category folder: '{item}' for '{target_category}'")
                return item_path
    
    _log_progress(f"DEBUG: No matching category folder found for '{target_category}'")
    return None

def create_old_images_folder(target_folder, category=None):
    """
    Create Old Images folder with optional category subfolder
    """
    old_images_path = os.path.join(target_folder, "Old Images")
    
    if category:
        old_images_path = os.path.join(old_images_path, category)
    
    if not os.path.exists(old_images_path):
        os.makedirs(old_images_path)
        _log_progress(f"DEBUG: Created Old Images folder: {old_images_path}")
    return old_images_path

def get_file_hash(filepath):
    hash_md5 = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()

def are_files_same(file1, file2):
    return normalize_filename(os.path.basename(file1)) == normalize_filename(os.path.basename(file2))

def handle_duplicate_files(file1, file2):
    """
    Properly handle duplicates by moving them to Old Images
    """
    if are_files_same(file1, file2) and filecmp.cmp(file1, file2, shallow=False):
        file2_dir = os.path.dirname(file2)
        file2_name = os.path.basename(file2)
        
        current_dir = file2_dir
        brand_dir = None
        
        for _ in range(3):
            parent_dir = os.path.dirname(current_dir)
            if parent_dir == current_dir:
                break
            
            try:
                subdirs = [d for d in os.listdir(parent_dir) 
                          if os.path.isdir(os.path.join(parent_dir, d))]
                if len(subdirs) > 1:
                    brand_dir = current_dir
                    break
            except (OSError, PermissionError):
                pass
            
            current_dir = parent_dir
        
        if not brand_dir:
            brand_dir = file2_dir
        
        file_category = get_file_category(file2_name)
        
        old_images_path = create_old_images_folder(brand_dir, file_category)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        basename, ext = os.path.splitext(file2_name)
        new_name = f"{basename}_duplicate_{timestamp}{ext}"
        
        old_file_path = os.path.join(old_images_path, new_name)
        shutil.move(file2, old_file_path)
        _log_progress(f"Moved duplicate to Old Images: {os.path.relpath(old_file_path, brand_dir)}")
        return True
    return False

def should_use_existing_brand_folder(brand_name, existing_folders):
    """
    Check if the brand should use an existing more specific folder.
    Returns the path to the more specific folder if found, None otherwise.
    """
    normalized_brand = normalize_name(brand_name)
    brand_words = set(brand_name.lower().replace('-', ' ').split())
    
    folder_candidates = []
    for folder_name, folder_path in existing_folders:
        folder_words = set(folder_name.lower().replace('-', ' ').split())
        folder_candidates.append((folder_name, folder_path, folder_words, len(folder_words)))
    
    folder_candidates.sort(key=lambda x: x[3], reverse=True)
    
    for folder_name, folder_path, folder_words, word_count in folder_candidates:
        if brand_words.issubset(folder_words) and word_count > len(brand_words):
            return folder_path
    
    return None

def find_existing_brand_folder(root_path, brand_name):
    """
    Find an existing brand folder that matches the given brand name.
    Only match folders that are actually the same brand, not combined brand+code folders.
    """
    if not brand_name:
        return None
        
    normalized_target = normalize_name(brand_name)
    target_words = set(brand_name.lower().split())
    
    _log_progress(f"DEBUG: Looking for brand folder '{brand_name}' (normalized: '{normalized_target}')")
    
    for item in os.listdir(root_path):
        item_path = os.path.join(root_path, item)
        if os.path.isdir(item_path):
            normalized_item = normalize_name(item)
            _log_progress(f"DEBUG: Checking folder '{item}' (normalized: '{normalized_item}')")
            
            if normalized_item == normalized_target:
                _log_progress(f"DEBUG: Found exact match: '{item}'")
                return item_path
    
    for item in os.listdir(root_path):
        item_path = os.path.join(root_path, item)
        if os.path.isdir(item_path):
            alt_name1 = brand_name.replace(' ', '-')
            alt_name2 = brand_name.replace('-', ' ')
            
            if (normalize_name(item) == normalize_name(alt_name1) or 
                normalize_name(item) == normalize_name(alt_name2)):
                _log_progress(f"DEBUG: Found separator variant match: '{item}'")
                return item_path
    
    _log_progress(f"DEBUG: No suitable brand folder found for '{brand_name}'")
    return None

def find_existing_product_folder(brand_path, product_code):
    """Find an existing product folder that matches the given product code"""
    if not product_code:
        return None
        
    normalized_target = normalize_name(product_code)
    
    _log_progress(f"DEBUG: Looking for product folder '{product_code}' in '{brand_path}'")
    
    for item in os.listdir(brand_path):
        item_path = os.path.join(brand_path, item)
        if os.path.isdir(item_path):
            normalized_item = normalize_name(item)
            _log_progress(f"DEBUG: Checking product folder '{item}' (normalized: '{normalized_item}')")
            
            if normalized_item == normalized_target:
                _log_progress(f"DEBUG: Found matching product folder: '{item}'")
                return item_path
    
    _log_progress(f"DEBUG: No matching product folder found for '{product_code}'")
    return None

def flatten_nested_folders(root_path):
    """Flatten folders that have nested folders with the same name"""
    _log_progress("\nStep 1: Flattening nested folders...")
    for dirpath, dirnames, filenames in os.walk(root_path, topdown=False):
        parent_name = os.path.basename(os.path.dirname(dirpath))
        current_name = os.path.basename(dirpath)
        
        if parent_name == current_name:
            parent_path = os.path.dirname(dirpath)
            _log_progress(f"Found nested folder: {dirpath}")
            
            for item in os.listdir(dirpath):
                src = os.path.join(dirpath, item)
                dst = os.path.join(parent_path, item)
                
                if os.path.exists(dst):
                    if os.path.isdir(dst):
                        for subitem in os.listdir(src):
                            sub_src = os.path.join(src, subitem)
                            sub_dst = os.path.join(dst, subitem)
                            if os.path.exists(sub_dst):
                                base, ext = os.path.splitext(subitem)
                                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                                new_name = f"{base}_{timestamp}{ext}"
                                sub_dst = os.path.join(dst, new_name)
                            shutil.move(sub_src, sub_dst)
                    else:
                        base, ext = os.path.splitext(item)
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        new_name = f"{base}_{timestamp}{ext}"
                        dst = os.path.join(parent_path, new_name)
                        shutil.move(src, dst)
                else:
                    shutil.move(src, dst)
            
            try:
                os.rmdir(dirpath)
                _log_progress(f"Flattened nested folder: {dirpath}")
            except OSError as e:
                _log_progress(f"Could not remove folder {dirpath}: {e}")

def organize_files_in_brand_folders(folder_path):
    """
    Updated to properly handle existing file conflicts
    """
    _log_progress(f"DEBUG: Organizing files in brand folders at: {folder_path}")
    
    for item in os.listdir(folder_path):
        item_path = os.path.join(folder_path, item)
        
        if (not os.path.isdir(item_path) or 
            item.lower().startswith('__webp to be move to the right folders')):
            continue
            
        _log_progress(f"DEBUG: Processing folder: {item}")
        
        for file in os.listdir(item_path):
            file_path = os.path.join(item_path, file)
            if os.path.isfile(file_path):
                basename = os.path.splitext(file)[0]
                _log_progress(f"DEBUG: Processing file: {file}")
                
                name, product_code, variant = extract_name_code_variant(basename)
                
                if not name:
                    name = item
                    _log_progress(f"DEBUG: Using folder name as brand: {name}")
                
                existing_brand = find_existing_brand_folder(folder_path, name)
                if existing_brand:
                    brand_folder = existing_brand
                    _log_progress(f"DEBUG: Using existing brand folder: {os.path.basename(brand_folder)}")
                else:
                    brand_folder = os.path.join(folder_path, name)
                    _log_progress(f"DEBUG: Creating new brand folder: {name}")
                
                os.makedirs(brand_folder, exist_ok=True)
                
                if product_code:
                    _log_progress(f"DEBUG: Looking for product folder: {product_code}")
                    existing_product = find_existing_product_folder(brand_folder, product_code)
                    if existing_product:
                        product_folder = existing_product
                        _log_progress(f"DEBUG: Using existing product folder: {os.path.basename(product_folder)}")
                    else:
                        product_folder = os.path.join(brand_folder, product_code)
                        _log_progress(f"DEBUG: Creating new product folder: {product_code}")
                    
                    os.makedirs(product_folder, exist_ok=True)
                    target_folder = product_folder
                else:
                    target_folder = brand_folder
                
                file_category = get_file_category(file)
                if file_category:
                    current_folder_name = os.path.basename(target_folder)
                    if not are_categories_equivalent(current_folder_name, file_category):
                        existing_category_folder = find_existing_category_folder(target_folder, file_category)
                        if existing_category_folder:
                            final_folder = existing_category_folder
                            _log_progress(f"DEBUG: Using existing category folder: {os.path.basename(final_folder)}")
                        else:
                            final_folder = os.path.join(target_folder, file_category)
                            _log_progress(f"DEBUG: Creating new category folder: {file_category}")
                        
                        os.makedirs(final_folder, exist_ok=True)
                        dst = os.path.join(final_folder, file)
                    else:
                        dst = os.path.join(target_folder, file)
                        _log_progress(f"DEBUG: File already in correct category folder")
                else:
                    dst = os.path.join(target_folder, file)
                
                if os.path.exists(dst):
                    _log_progress(f"DEBUG: File already exists at destination: {dst}")
                    file_category = get_file_category(file)
                    old_images_folder = create_old_images_folder(target_folder, file_category)
                    handle_existing_file(dst, old_images_folder)
                
                try:
                    shutil.move(file_path, dst)
                    _log_progress(f"DEBUG: Moved {file} to: {os.path.relpath(dst, folder_path)}")
                except Exception as e:
                    _log_progress(f"ERROR: Failed to move {file}: {e}")

def organize_folder_contents(folder_path, is_webp_folder=False):
    """Organize folder contents with proper Old Images handling"""
    for root, dirs, files in os.walk(folder_path, topdown=False):
        if root == folder_path and not is_webp_folder:
            continue
            
        for filename in files:
            if '.' not in filename:
                continue

            file_path = os.path.join(root, filename)
            basename = os.path.splitext(filename)[0]
            
            name, product_code, variant = extract_name_code_variant(basename)

            if not name:
                _log_progress(f"Skipped '{filename}': couldn't determine name.")
                continue

            if is_webp_folder:
                main_folder = os.path.dirname(folder_path)
                existing_brand = find_existing_brand_folder(main_folder, name)
                if existing_brand:
                    name_folder_path = existing_brand
                    _log_progress(f"Using existing brand folder for WEBP: {os.path.basename(name_folder_path)}")
                else:
                    name_folder_path = os.path.join(folder_path, name)
                    _log_progress(f"Creating new brand folder for WEBP: {os.path.basename(name_folder_path)}")
                
                os.makedirs(name_folder_path, exist_ok=True)
                
                if product_code:
                    existing_product = find_existing_product_folder(name_folder_path, product_code)
                    if existing_product:
                        product_folder_path = existing_product
                        _log_progress(f"Using existing product folder for WEBP: {os.path.basename(product_folder_path)}")
                    else:
                        product_folder_path = os.path.join(name_folder_path, product_code)
                        _log_progress(f"Creating new product folder for WEBP: {os.path.basename(product_folder_path)}")
                    
                    os.makedirs(product_folder_path, exist_ok=True)
                    target_folder = product_folder_path
                else:
                    target_folder = name_folder_path
                
                file_category = get_file_category(filename)
                if file_category:
                    current_folder_name = os.path.basename(target_folder)
                    if not are_categories_equivalent(current_folder_name, file_category):
                        existing_category_folder = find_existing_category_folder(target_folder, file_category)
                        if existing_category_folder:
                            final_folder_path = existing_category_folder
                        else:
                            final_folder_path = os.path.join(target_folder, file_category)
                        
                        os.makedirs(final_folder_path, exist_ok=True)
                        dst = os.path.join(final_folder_path, filename)
                    else:
                        dst = os.path.join(target_folder, filename)
                else:
                    dst = os.path.join(target_folder, filename)
                
                try:
                    if file_path != dst:
                        if os.path.exists(dst):
                            file_category = get_file_category(filename)
                            old_images_folder = create_old_images_folder(target_folder, file_category)
                            handle_existing_file(dst, old_images_folder)
                        shutil.move(file_path, dst)
                        _log_progress(f"Organized in WEBP folder: {os.path.relpath(dst, folder_path)}")
                except Exception as e:
                    _log_progress(f"Error moving {filename}: {str(e)}")
            else:
                file_category = get_file_category(filename)
                if file_category:
                    current_dir = os.path.basename(os.path.normpath(root))
                    if not are_categories_equivalent(current_dir, file_category):
                        existing_category_folder = find_existing_category_folder(root, file_category)
                        if existing_category_folder:
                            final_folder_path = existing_category_folder
                        else:
                            final_folder_path = os.path.join(root, file_category)
                        
                        os.makedirs(final_folder_path, exist_ok=True)
                        dst = os.path.join(final_folder_path, filename)
                    else:
                        dst = os.path.join(root, filename)
                    
                    try:
                        if file_path != dst:
                            if os.path.exists(dst):
                                file_category = get_file_category(filename)
                                old_images_folder = create_old_images_folder(root, file_category)
                                handle_existing_file(dst, old_images_folder)
                            shutil.move(file_path, dst)
                            _log_progress(f"Organized in main folder: {os.path.relpath(dst, folder_path)}")
                    except Exception as e:
                        _log_progress(f"Error moving {filename}: {str(e)}")

def find_matching_folder(target_root, folder_name):
    """Find matching folder with improved multi-word name handling"""
    normalized_target = normalize_name(folder_name)
    
    for item in os.listdir(target_root):
        if os.path.isdir(os.path.join(target_root, item)):
            normalized_item = normalize_name(item)
            
            if normalized_item == normalized_target:
                return os.path.join(target_root, item)
            
            if normalized_item == normalize_name(folder_name.replace(' ', '-')):
                return os.path.join(target_root, item)
            if normalized_item == normalize_name(folder_name.replace('-', ' ')):
                return os.path.join(target_root, item)
    
    return None

def merge_folders(source_path, target_path):
    """
    Updated merge function to properly handle file conflicts
    """
    for item in os.listdir(source_path):
        src_item_path = os.path.join(source_path, item)
        
        if os.path.isdir(src_item_path):
            target_item_path = find_matching_folder(target_path, item)
            
            if not target_item_path:
                target_item_path = os.path.join(target_path, item)
            
            if os.path.exists(target_item_path):
                merge_folders(src_item_path, target_item_path)
            else:
                shutil.move(src_item_path, target_item_path)
                _log_progress(f"Moved new folder {item} to {target_path}")
        else:
            file_category = get_file_category(item)
            if file_category:
                current_dir = os.path.basename(os.path.normpath(target_path))
                if not are_categories_equivalent(current_dir, file_category):
                    existing_category_folder = find_existing_category_folder(target_path, file_category)
                    if existing_category_folder:
                        final_folder = existing_category_folder
                    else:
                        final_folder = os.path.join(target_path, file_category)
                        os.makedirs(final_folder, exist_ok=True)
                    
                    dst = os.path.join(final_folder, item)
                else:
                    dst = os.path.join(target_path, item)
            else:
                dst = os.path.join(target_path, item)
            
            if os.path.exists(dst):
                if handle_duplicate_files(src_item_path, dst):
                    continue
                else:
                    base, ext = os.path.splitext(item)
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    new_name = f"{base}_conflict_{timestamp}{ext}"
                    dst = os.path.join(os.path.dirname(dst), new_name)
            
            try:
                shutil.move(src_item_path, dst)
                _log_progress(f"Moved file {item} to {os.path.relpath(dst, target_path)}")
            except Exception as e:
                _log_progress(f"Error moving {item}: {e}")

def handle_existing_file(existing_file_path, old_images_folder):
    """Handle existing files by moving them to Old Images with timestamp"""
    filename = os.path.basename(existing_file_path)
    base, ext = os.path.splitext(filename)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    new_name = f"{base}_replaced_{timestamp}{ext}"
    
    old_file_path = os.path.join(old_images_folder, new_name)
    
    try:
        shutil.move(existing_file_path, old_file_path)
        _log_progress(f"Moved existing file to Old Images: {os.path.relpath(old_file_path)}")
    except Exception as e:
        _log_progress(f"Error moving existing file to Old Images: {e}")

def remove_empty_folders(folder_path):
    """Remove empty folders recursively, but preserve WEBP folder"""
    _log_progress(f"\nStep 6: Removing empty folders...")
    for root, dirs, files in os.walk(folder_path, topdown=False):
        for dir_name in dirs:
            dir_path = os.path.join(root, dir_name)
            
            if dir_name.lower().startswith('__webp to be move to the right folders'):
                _log_progress(f"Preserving WEBP folder: {os.path.relpath(dir_path, folder_path)}")
                continue
                
            try:
                if not os.listdir(dir_path):
                    os.rmdir(dir_path)
                    _log_progress(f"Removed empty folder: {os.path.relpath(dir_path, folder_path)}")
            except OSError:
                pass

def move_webp_folders_to_main(main_folder):
    """Move folders from WEBP folder to main folder structure"""
    webp_folder_path = None
    
    for item in os.listdir(main_folder):
        item_path = os.path.join(main_folder, item)
        if (os.path.isdir(item_path) and 
            item.lower().startswith('__webp to be move to the right folders')):
            webp_folder_path = item_path
            break
    
    if not webp_folder_path:
        _log_progress("No WEBP folder found to move")
        return
    
    _log_progress(f"Found WEBP folder: {webp_folder_path}")
    
    for item in os.listdir(webp_folder_path):
        source_folder = os.path.join(webp_folder_path, item)
        
        if os.path.isdir(source_folder):
            existing_folder = find_matching_folder(main_folder, item)
            
            if existing_folder:
                _log_progress(f"Merging {item} with existing folder {os.path.basename(existing_folder)}")
                merge_folders(source_folder, existing_folder)
            else:
                target_folder = os.path.join(main_folder, item)
                shutil.move(source_folder, target_folder)
                _log_progress(f"Moved {item} to main folder")
    
    try:
        if not os.listdir(webp_folder_path):
            os.rmdir(webp_folder_path)
            _log_progress(f"Removed empty WEBP folder")
    except OSError:
        _log_progress(f"WEBP folder not empty, keeping it")

def organize_files_web(folder_path):
    """Main function to orchestrate the file organization process for web"""
    global _progress_messages
    _progress_messages = [] # Clear messages for a new run

    if not os.path.exists(folder_path):
        _log_progress(f"Error: Folder '{folder_path}' does not exist.")
        return False, _progress_messages
    
    _log_progress(f"Starting organization of: {folder_path}")
    
    flatten_nested_folders(folder_path)
    
    webp_folder = None
    for item in os.listdir(folder_path):
        item_path = os.path.join(folder_path, item)
        if (os.path.isdir(item_path) and 
            item.lower().startswith('__webp to be move to the right folders')):
            webp_folder = item_path
            break
    
    if webp_folder:
        _log_progress(f"\nStep 2: Organizing WEBP folder contents...")
        organize_folder_contents(webp_folder, is_webp_folder=True)
        
        _log_progress(f"\nStep 3: Moving WEBP folders to main structure...")
        move_webp_folders_to_main(folder_path)
    
    _log_progress(f"\nStep 4: Organizing files in brand folders...")
    organize_files_in_brand_folders(folder_path)
    
    _log_progress(f"\nStep 5: Organizing remaining folder contents...")
    organize_folder_contents(folder_path)
    
    remove_empty_folders(folder_path)
    
    _log_progress(f"\nOrganization complete!")
    return True, _progress_messages

# This part is for local testing of b-up.py, not used by Flask app
if __name__ == "__main__":
    # Example usage for local testing
    # folder_to_organize = input("Enter the path to the folder you want to organize: ").strip().strip('"')
    # success, messages = organize_files_web(folder_to_organize)
    # for msg in messages:
    #     print(msg)
    pass
