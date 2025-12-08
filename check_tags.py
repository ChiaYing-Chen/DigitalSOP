import re

def check_tags(filename):
    with open(filename, 'r', encoding='utf-8') as f:
        content = f.read()

    # Extract HTML_TEMPLATE
    start_marker = 'HTML_TEMPLATE = """'
    end_marker = '"""' # Assuming it ends with this at the end of file or usually
    
    start_idx = content.find(start_marker)
    if start_idx == -1:
        print("HTML_TEMPLATE not found")
        return

    start_idx += len(start_marker)
    # Just take the rest of the file or find the end
    # Note: The file might have code after, but looking at view_file, it looks like it's at the end or close.
    # Actually step 5 shows HTML_TEMPLATE starts at 323.
    
    html_content = content[start_idx:]
    
    # We only care about the Editor component roughly, or just check generic balance
    # But JSX has { } which makes regex parsing hard.
    # However, standard HTML tags should be balanced.
    
    lines = html_content.split('\n')
    stack = []
    
    # Simple parser: look for <tag> and </tag>
    # Ignore self closing <tag />
    # Ignore void tags (img, input, br, hr, meta, link)
    
    void_tags = {'img', 'input', 'br', 'hr', 'meta', 'link'}
    
    for i, line in enumerate(lines):
        # Remove comments logic is hard, but let's try simple regex
        # Remove {/* ... */}
        line = re.sub(r'\{\/\*.*?\*\/\}', '', line)
        
        # Find tags
        matches = re.finditer(r'<\/?([a-zA-Z0-9]+)[^>]*\/?>', line)
        for match in matches:
            tag_str = match.group(0)
            tag_name = match.group(1)
            
            if tag_name in void_tags:
                continue
                
            if tag_str.endswith('/>'):
                continue
                
            if tag_str.startswith('</'):
                # Closing tag
                if not stack:
                    print(f"Error: Unexpected closing tag </{tag_name}> at line {i+1}: {line.strip()}")
                    return
                last_tag = stack.pop()
                if last_tag != tag_name:
                    print(f"Error: Mismatched closing tag </{tag_name}> at line {i+1}. Expected </{last_tag}>. Line: {line.strip()}")
                    # Don't return, keep checking to see more
            else:
                # Opening tag
                stack.append(tag_name)
                
    if stack:
        print(f"Error: Unclosed tags at end: {stack}")
    else:
        print("Tags seem balanced.")

check_tags('d:\\W52_DigitalSOP\\app.py')
