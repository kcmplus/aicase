import test from 'node:test';
import assert from 'node:assert/strict';
import {visibleSettings,settingsItems} from '../admin/src/settings-navigation.js';

test('settings navigation keeps superuser-only integrations hidden from ordinary staff',()=>{
 assert.deepEqual(visibleSettings(null),[]);
 assert.deepEqual(visibleSettings({permissions:[]}),[]);
 const staff={is_superuser:false,permissions:['management_api.view_smtpconfig','management_api.view_deviceconnection','management_api.view_aiserviceconfig','management_api.view_stripeconfig','management_api.view_pricingplan']};
 assert.deepEqual(visibleSettings(staff).map(i=>i.key),['plans']);
 assert.equal(visibleSettings({is_superuser:true,permissions:[]}).length,settingsItems.length);
});
test('settings access preserves existing independent staff view permissions',()=>{
 const user={permissions:['auth.view_user','management_api.view_auditlog']};
 assert.deepEqual(visibleSettings(user).map(i=>i.key),['users','audit-logs']);
 assert.ok(settingsItems.every(i=>i.path.startsWith('/settings/')));
});
