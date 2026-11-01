import assert from 'node:assert/strict';
import {hasWebUpdate,refreshUrl} from '../../frontends/web/app/src/updates.js';
const current='a'.repeat(16), next='b'.repeat(16);
assert.equal(hasWebUpdate(current,{version:current,status:200}),false);
assert.equal(hasWebUpdate(current,{version:next,status:200}),true);
assert.equal(hasWebUpdate(current,{version:next,status:200,_disconnected:true}),false);
for (const release of [null,{version:next,status:500},{version:'1.21.4',status:200},{version:next,status:0}]) {
  assert.equal(hasWebUpdate(current,release),false);
}
const href='https://bc250cc.local:8250/?v='+next+'#/gpu';
const first=refreshUrl(href,next,1),second=refreshUrl(first,next,2);
assert.notEqual(first,second);
assert.equal(new URL(second).hash,'#/gpu');
assert.equal(new URL(second).searchParams.get('v'),next);
console.log('PASS: current and new builds, failed/offline probes, invalid versions, repeated fresh navigation and route preservation');

const {jobState} = await import('../../frontends/web/app/src/jobs.js');
assert.equal(jobState({status:200,id:0}),'idle');
assert.equal(jobState({status:200,id:12,done:false,kind:'gddr6.monitor'}),'job');
assert.equal(jobState({status:200,id:12,done:true}),'job');
for (const payload of [null,{status:0},{status:500,error:'offline'},{status:200,ok:false,error:'Terminal disconnected'},
                       {status:200,id:12},{status:200,id:0,error:'Failed'}, {status:200,id:'12',done:false}]) {
  assert.equal(jobState(payload),'unavailable');
}
console.log('PASS: absent jobs clear activity; invalid and failed probes never replace the active job');
