"""Check the Git-visible source set for accidental private data.

From v1.2.0 the repository intentionally ships the firmware package
(`vendor/`, `inputs/`, `toolbox/firmware/`). Those files are non-MIT factory
derived binaries, so they are allow-listed here by exact path instead of being
treated as an accident.

SPDX-License-Identifier: MIT.
"""
import re,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
# Deliberately bundled (see THIRD_PARTY_NOTICES.md): factory inputs + snapshot.
BUNDLED={'inputs/ips-stock.bin','inputs/main-stock.bin','inputs/libISP585.a',
         'toolbox/firmware/main.bin','toolbox/firmware/ips.bin',
         'toolbox/firmware/s1-full.gif','toolbox/firmware/s1-lite.gif',
         'toolbox/firmware/s1-blank.gif','toolbox/firmware/preview.png',
         'toolbox/firmware/info.json','toolbox/firmware/main.json','toolbox/firmware/ips.json'}
def files():
 data=subprocess.check_output(['git','ls-files','-z','--cached','--others','--exclude-standard'],cwd=ROOT)
 return sorted(set(p.decode('utf8') for p in data.split(b'\0') if p))
def check():
 problems=[];paths=files()
 for name in paths:
  p=ROOT/name
  if not p.is_file():continue
  if name in BUNDLED:continue
  if p.suffix.lower() in ['.bin','.elf','.a','.o','.map','.log'] or p.name=='main-clock-isp-blob.h' or name.startswith('build/') or name.startswith('llvm/'):
   problems.append(name+': generated or toolchain file outside the documented bundle')
  if p.suffix.lower() not in ['.md','.txt','.py','.mjs','.cjs','.js','.ps1','.json','.html','.css','.yml','.ld','.c','.h']:continue
  text=p.read_text(encoding='utf8')
  for pattern in [r'(?i)pet_[0-9a-f]{16,}',r'(?i)(?:C|F):[/\\](?:Users|codexproject)[/\\]',r'gh[pousr]_[A-Za-z0-9]{20,}',r'sk-(?:proj-)?[A-Za-z0-9_-]{24,}',r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----']:
   if re.search(pattern,text):problems.append(name+': possible private data')
  if name!='tools/check_release.py' and re.search(r'(?i)furina|芙宁娜|quota-studio|work/rainy75|outputs/Rainy75',text):problems.append(name+': private asset or workspace reference')
  if p.suffix=='.md':
   for target in re.findall(r'\]\(([^)]+)\)',text):
    if re.match(r'^[a-z]+:|^#',target):continue
    target=target.split('#',1)[0]
    if target and not (p.parent/target).exists():problems.append(name+': missing link '+target)
 if problems:raise SystemExit('\n'.join(problems))
 print(f'Checked {len(paths)} Git-visible source files: no unexpected input, common secret pattern or missing Markdown link found.')
if __name__=='__main__':check()
