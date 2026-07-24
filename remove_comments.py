import os

directories = ['.', 'agent', 'app']
for d in directories:
    for f in os.listdir(d):
        if f.endswith('.py') and os.path.isfile(os.path.join(d, f)):
            filepath = os.path.join(d, f)
            with open(filepath, 'r', encoding='utf-8') as file:
                lines = file.readlines()
            
            new_lines = []
            for line in lines:
                stripped = line.strip()
                if stripped.startswith('#'):
                    continue
                
                if ' #' in line and '"' not in line and "'" not in line:
                    line = line.split(' #')[0] + '\n'
                    
                new_lines.append(line)
                
            with open(filepath, 'w', encoding='utf-8') as file:
                file.writelines(new_lines)

print("Comments removed.")
