import {spawnSync} from 'node:child_process';
const python=process.env.E2E_PYTHON || (process.platform==='win32'?'.venv/Scripts/python.exe':'python');
function run(command,args,cwd=process.cwd()) {
  const env=cwd==='backend'?{...process.env,DATABASE_URL:'sqlite://',AUTH_PG_TEST_URL:'',MEDIA_ROOT:'.test-media'}:process.env;
  const result=spawnSync(command,args,{cwd,env,stdio:'inherit',shell:process.platform==='win32'&&command==='npm'});
  if(result.error) throw result.error;
  if(result.status!==0) process.exit(result.status||1);
}
run('npm',['test']);
run(python.startsWith('.')?'../'+python:python,['-m','pytest','-q'],'backend');
run('npm',['run','test:e2e']);
