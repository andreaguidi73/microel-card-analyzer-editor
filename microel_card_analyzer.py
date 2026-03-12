import sys
import os
import re

def read_mct_file(file_path):
    """
    Read MCT file and extract block 0 (32-character hex string).
    MCT files can be in text or binary format.
    
    Args:
        file_path: Path to the .mct file
        
    Returns:
        32-character hex string representing block 0, or None if failed
    """
    try:
        # Try reading as text first (common MCT format)
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        # Extract hex strings from the file
        hex_patterns = re.findall(r'[0-9A-Fa-f]{32}', content)
        if hex_patterns:
            return hex_patterns[0]  # Return block 0
        
        # If no text hex found, try binary
        with open(file_path, 'rb') as f:
            data = f.read()
            # Look for 32-byte blocks (16 bytes = 32 hex chars)
            if len(data) >= 16:
                block_0 = data[:16].hex().upper()
                return block_0
    except Exception as e:
        print(f"Error reading MCT file: {e}")
        return None
    
    return None

def read_nfc_file(file_path):
    """
    Read Flipper Zero NFC file and extract block 0.
    
    Args:
        file_path: Path to the .nfc file
        
    Returns:
        32-character hex string representing block 0, or None if failed
    """
    try:
        with open(file_path, 'r') as f:
            content = f.read()
        # Extract block 0 from NFC format
        hex_patterns = re.findall(r'Block\s+0:\s+([0-9A-Fa-f\s]{32,})', content)
        if hex_patterns:
            return hex_patterns[0].replace(' ', '')
    except Exception as e:
        print(f"Error reading NFC file: {e}")
        return None
    
    return None

def color_string(input_string):
    """
    Parse hex string and apply color formatting with schema.
    
    Parameters:
    1. Operation number: 4 characters (2 bytes)
    2. Total input sum: 4 characters (2 bytes)
    3. Deposit: 2 characters (1 byte)
    4. Credit: 4 characters (2 bytes)
    5. Transaction date: 8 characters (4 bytes)
    6. Points: 4 characters (2 bytes)
    7. Last transaction amount: 4 characters (2 bytes)
    8. Checksum: 2 characters (1 byte)
    """
    colors = ["\033[96m", "\033[36m", "\033[35m", "\033[34m", "\033[33m"]
    reset = "\033[0m"
    
    schema = [
        (4, "Operation number"),
        (4, "Total input sum"),
        (2, "Deposit"),
        (4, "Credit"),
        (8, "Transaction date"),
        (4, "Points"),
        (4, "Last transaction amount"),
        (2, "Checksum")
    ]
    
    result = []
    color_index = 0
    char_index = 0
    
    for length, description in schema:
        segment = input_string[char_index:char_index+length]
        colored_segment = colors[color_index] + segment + reset
        inverted_segment = ''.join(reversed([segment[i:i+2] for i in range(0, len(segment), 2)]))
        decimal_value = int(inverted_segment, 16)
        result.append((description, segment, colored_segment, inverted_segment, decimal_value))
        char_index += length
        color_index = (color_index + 1) % len(colors)
    
    return result

def hex_to_euros(hex_credit):
    """
    Convert hex credit value to euros with 2 decimal places.
    Credit is stored as little-endian hex (byte-inverted).
    
    Args:
        hex_credit: 4-character hex string
        
    Returns:
        Float value in euros
    """
    inverted = ''.join(reversed([hex_credit[i:i+2] for i in range(0, len(hex_credit), 2)]))
    credit_cents = int(inverted, 16)
    euros = credit_cents / 100.0
    return euros

def euros_to_hex(euro_value, length=4):
    """
    Convert euro value back to hex format (little-endian).
    
    Args:
        euro_value: Float or string value in euros (e.g., 10.50, "10,50")
        length: Output hex string length (default 4 for credit field)
        
    Returns:
        Hex string in little-endian format, or None if invalid
    """
    try:
        # Handle input with or without € symbol, comma or period
        euro_str = str(euro_value).replace('€', '').replace(',', '.').strip()
        cents = int(float(euro_str) * 100)
        
        # Convert to hex and invert (little-endian)
        hex_value = f"{cents:0{length}X}"
        inverted = ''.join(reversed([hex_value[i:i+2] for i in range(0, len(hex_value), 2)]))
        return inverted
    except ValueError:
        return None

def print_data(parsed_data):
    """
    Display parsed data with special formatting for credit (shown in euros).
    """
    print("\nFull colored string:")
    print(''.join(colored for _, _, colored, _, _ in parsed_data))
    
    print("\nParsed data:")
    for i, (description, original, colored, inverted, decimal) in enumerate(parsed_data):
        # Special handling for credit parameter (index 3)
        if i == 3:  # Credit parameter
            euros = hex_to_euros(original)
            print(f"{description}: {colored} (Decimal: {decimal}, € {euros:.2f})")
        else:
            print(f"{description}: {colored} (Inverted: {inverted}, Decimal: {decimal})")

def modify_parameter(parsed_data):
    """
    Allow user to modify parameters.
    Special handling for credit: accepts euro input directly.
    """
    print("\nChoose a parameter to modify:")
    for i, (description, _, _, _, _) in enumerate(parsed_data):
        print(f"{i + 1}. {description}")
    
    try:
        choice = int(input("Enter the number of the parameter to modify: ")) - 1
    except ValueError:
        print("Invalid input.")
        return parsed_data
    
    if choice < 0 or choice >= len(parsed_data):
        print("Invalid choice.")
        return parsed_data

    description, original, colored, inverted, decimal = parsed_data[choice]
    length = len(original)

    # Special handling for credit (index 3)
    if choice == 3:  # Credit parameter
        print("\nEnter the credit value in euros (e.g., 10.50 or 10,50):")
        new_euro = input("New value: ").strip()
        new_hex = euros_to_hex(new_euro, length)
        
        if new_hex is None:
            print("Invalid euro value. Please enter a valid number.")
            return parsed_data
        
        euros_float = float(new_euro.replace(',', '.'))
        new_inverted = new_euro.replace('€', '').replace(',', '.').strip()
        new_decimal = int(euros_float * 100)
    else:
        # Standard modification for other parameters
        print("\nChoose the format of the new value:")
        print("1. HEX")
        print("2. HEX INVERTED")
        print("3. DECIMAL")
        format_choice = input("Enter the number of your choice: ")

        if format_choice not in ['1', '2', '3']:
            print("Invalid format choice.")
            return parsed_data

        new_value = input("Enter the new value: ")

        if format_choice == '1':  # HEX
            new_hex = new_value.zfill(length).upper()
            new_inverted = ''.join(reversed([new_hex[i:i+2] for i in range(0, len(new_hex), 2)]))
            new_decimal = int(new_inverted, 16)
        elif format_choice == '2':  # HEX INVERTED
            new_inverted = new_value.zfill(length).upper()
            new_hex = ''.join(reversed([new_inverted[i:i+2] for i in range(0, len(new_inverted), 2)]))
            new_decimal = int(new_inverted, 16)
        else:  # DECIMAL
            new_decimal = int(new_value)
            new_inverted = f"{new_decimal:0{length}X}"
            new_hex = ''.join(reversed([new_inverted[i:i+2] for i in range(0, len(new_inverted), 2)]))

    new_colored = parsed_data[choice][2].replace(original, new_hex)
    parsed_data[choice] = (description, new_hex, new_colored, new_inverted, new_decimal)

    # Reconstruct the full string
    full_string = ''.join(segment for _, segment, _, _, _ in parsed_data)
    return color_string(full_string)

def save_to_file(parsed_data, output_path):
    """
    Save modified data to output file.
    
    Args:
        parsed_data: List of parsed parameter tuples
        output_path: Path where to save the file
        
    Returns:
        True if successful, False otherwise
    """
    try:
        hex_string = ''.join(segment for _, segment, _, _, _ in parsed_data)
        with open(output_path, 'w') as f:
            f.write(hex_string)
        print(f"\n✓ Data saved to {output_path}")
        return True
    except Exception as e:
        print(f"Error saving file: {e}")
        return False

def main():
    """
    Main function with support for:
    - .mct files (new)
    - .nfc files (existing)
    - Direct hex strings (existing)
    """
    
    # Get input source
    if len(sys.argv) > 1:
        input_source = sys.argv[1]
    else:
        input_source = input("Enter file path (.mct, .nfc) or 32-char hex string: ").strip()
    
    # Determine input type and load data
    input_string = None
    source_file = None
    
    if input_source.lower().endswith('.mct'):
        # Read MCT file
        print(f"Reading MCT file: {input_source}")
        input_string = read_mct_file(input_source)
        source_file = input_source
        
        if input_string is None:
            print("Error: Could not extract block 0 from MCT file.")
            return
        print(f"✓ Block 0 extracted: {input_string}")
        
    elif input_source.lower().endswith('.nfc'):
        # Read NFC file (Flipper Zero format)
        print(f"Reading NFC file: {input_source}")
        input_string = read_nfc_file(input_source)
        source_file = input_source
        
        if input_string is None:
            print("Error: No block 0 found in NFC file.")
            return
        print(f"✓ Block 0 extracted: {input_string}")
        
    else:
        # Assume hex string input
        input_string = input_source.replace(' ', '').upper()
    
    # Validate hex string
    if len(input_string) != 32:
        print(f"Error: The input string must be exactly 32 characters long (got {len(input_string)}).")
        return
    
    if not re.match(r'^[0-9A-Fa-f]{32}$', input_string):
        print("Error: Invalid hex string format.")
        return
    
    # Process data
    parsed_data = color_string(input_string)
    
    # Interactive modification loop
    while True:
        print_data(parsed_data)
        
        choice = input("\nDo you want to modify a parameter? (y/n): ").lower()
        if choice != 'y':
            break
        
        parsed_data = modify_parameter(parsed_data)
    
    # Ask to save
    save_choice = input("\nDo you want to save the modified data? (y/n): ").lower()
    if save_choice == 'y':
        if source_file:
            default_output = f"{source_file}.modified"
            output_file = input(f"Enter output file path (default: {default_output}): ").strip()
            if not output_file:
                output_file = default_output
        else:
            output_file = input("Enter output file path: ").strip()
        
        if output_file:
            save_to_file(parsed_data, output_file)

if __name__ == "__main__":
    main()