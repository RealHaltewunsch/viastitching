"""Build a local testing PCM ZIP directly from a committed revision."""
import hashlib,json,os,subprocess,sys,zipfile
from pathlib import Path

root=Path(__file__).resolve().parent
output=Path(sys.argv[1]);output.mkdir(parents=True,exist_ok=True)
git=os.environ.get('GIT_BIN','git')
sha=subprocess.check_output([git,'rev-parse','HEAD'],cwd=root,text=True).strip()
def source(name):return subprocess.check_output([git,'show',sha+':'+name],cwd=root)
files={'metadata.json':'metadata.json','resources/icon.png':'viastitcher64x64.png'}
for name in ('__init__.py','defaults.json','localization.py','geometric_engine.py','density_field.py','native_geometry.py','project_rules.py','viastitcher.png','viastitcher_dialog.py','viastitcher_gui.py','viastitcher_plugin.py'):
 files['plugins/'+name]=name
for name in subprocess.check_output([git,'ls-files','locale'],cwd=root,text=True).splitlines():files['plugins/'+name]=name
metadata=json.loads(source('metadata.json'));version=metadata['versions'][0]['version']
assert metadata['versions'][0]['status']=='testing','Testing package only'
archive=output/('viastitcher-'+version+'-geometric-pcm.zip')
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
 for target,name in sorted(files.items()):
  data=source(name)
  if name.endswith('.py'):compile(data,name,'exec')
  z.writestr(target,data)
with zipfile.ZipFile(archive) as z:
 assert z.testzip() is None
 for target,name in files.items():assert z.read(target)==source(name)
checksum=hashlib.sha256(archive.read_bytes()).hexdigest()
(output/(archive.name+'.sha256')).write_text(checksum+'  '+archive.name+'\n')
(output/'source.json').write_text(json.dumps({'commit':sha,'sha256':checksum,'files':len(files),'version':version},indent=2))
print(archive);print('Source commit:',sha);print('SHA256:',checksum)
