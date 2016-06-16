import cssdk, time
import subprocess
import re
import time
from pysphere import VIServer
from subprocess import Popen, PIPE

API_ID = "***"
API_KEY = "*****"

def main():

    project_id = get_project_id()
    blueprint_id = get_blueprint_id()
    policy_id = get_policy_id()
    snapshot_id = get_snapshot_id(project_id, blueprint_id)
    env_id = post_env(project_id, policy_id, blueprint_id, snapshot_id)
    fqdn = get_env_status(env_id)
    state = openvpn_connect(fqdn["centos"])
    if state == False:
        print "vpn connection not established. Timeout waiting for connect"
        kill_vpn()
        return

    start_vm(fqdn["vcenter"])

    end_time = time.time()+60
    state_vm = False
    while not state_vm and time.time() < end_time:
        proc_ssh=Popen("ssh -o StrictHostKeyChecking=no -i ssh_certs/cloudify-manager-kp.pem root@10.35.20.2 'hostname'", shell=True, stdout=PIPE, stderr=PIPE)
        proc_ssh.wait()
        cmd_output = proc_ssh.communicate()
        if proc_ssh.returncode:
            print "Waiting for DHCP server vm to boot..."
        else:
            print 'Hostname: ', cmd_output[0]
            state_vm = True
        time.sleep(10)
    kill_vpn()
    delete_env(env_id)

def get_project_id():
    projects = get('projects/')
    return projects[0]['id']

def get_blueprint_id():
    blueprints = get('blueprints/')
    for elem in blueprints:
        if elem["name"] == '***':
            return elem["id"]

def get_policy_id():
    policy = get('policies/')
    return policy[0]['id']

def get_snapshot_id(project_id, blueprint_id):
    snapshot = get("projects/{0}/blueprints/{1}/".format(project_id, blueprint_id))
    temp = snapshot["createFromVersions"]
    return temp[1]["id"]

def post_env(project_id, policy_id, blueprint_id, snapshot_id):
    env = post('envs/',{
                        "environment": {
                            "name": "Test Environment",
                            "description": "Test Environment Description",
                            "projectId": project_id,
                            "policyId": policy_id
                            },
                        "itemsCart": [
                            {
                                "type": 1,
                                "blueprintId": blueprint_id,
                                "snapshotId": snapshot_id
                            }
                        ]
    })
    print "New Environment has been created successfully."
    return env["environmentId"]

def get_env_status(env_id):
    status_text = False
    while not status_text:
        time.sleep(50)
        env_status = get('/envs/actions/getExtended', {'envId': env_id})['statusText']
        print env_status
        if env_status == "Ready":
            status_text = True
    fqdn_names = get('/envs/actions/getExtended', {'envId': env_id})['vms']
    for elem in fqdn_names:
        if elem['name'] == 'Jump-node':
            fqdn = {"centos": elem['fqdn']}
            #print elem['fqdn']
        if elem['name'] == 'vCenter-Server':
            fqdn["vcenter"] = elem['fqdn']
    return fqdn

def openvpn_connect(fqdn_srv_name):

    print fqdn_srv_name

    f = open('client/client.ovpn', 'r')
    file = open('client/client_conf.ovpn', 'w')

    for line in f.readlines():
        match = re.search(r'^remote .+ 1194', line)
        if match:
            line = "remote {0} 1194\n".format(fqdn_srv_name)
        file.write(line)
    f.close()
    file.close()

    subprocess.call("cd client && sudo openvpn --config client_conf.ovpn 2>&1 > openvpn_log.txt &", shell=True)

    end_time = time.time()+60
    state = False
    while not state and time.time() < end_time:
        print("Waiting for ssh-openvpn vm to boot...")
        logfile = open('client/openvpn_log.txt', 'r')
        for line_match in logfile.readlines():
            match = re.search(r'.+Completed$', line_match)
            if match:
                state = True
                print "vpn connection established"
        logfile.close()
        time.sleep(10)
    return state

def start_vm(vcenter_fqdn):
    server = VIServer()
    vcenter_state = False
    end_time = time.time()+600
    while time.time() < end_time:
        try:
            server.connect(vcenter_fqdn, "login", "password")
            vm = server.get_vm_by_path("[datastore1] DHCP-server/DHCP-server.vmx")
            #vm.power_on()
            vcenter_state = True
            print vm.get_status()
            return
        except:
            print ("Waiting for vCenter vm to boot...")
            time.sleep(10)
    if not vcenter_state:
        print "Time out waiting for vCenter vm to boot."
        kill_vpn()

def kill_vpn():

    proc = Popen("ps -aux | awk '/sudo\ openvpn\ --config\ client_conf.ovpn/ {print $2}'", shell=True, stdout=PIPE)
    proc.wait()
    res = proc.communicate()
    if proc.returncode:
        print res[1]
    subprocess.call("sudo kill {0}".format(res[0]), shell=True)
    print "Openvpn was stoped"
    return

def delete_env(env_id):
    env = delete("envs/{0}/".format(env_id))
    print "Enviroment was removed"

def post(path, content=None):
	return request('POST', path, content=content)

def get(path, queryParams=None):
	return request('GET', path, queryParams=queryParams)

def delete(path, content=None):
	return request('DELETE', path, content=content)

def request(method, path, queryParams=None, content=None):
	res = cssdk.req(hostname="use.cloudshare.com",
					 method=method,
					 apiId=API_ID,
					 apiKey=API_KEY,
					 path=path,
					 queryParams=queryParams,
					 content=content)
	if res.status / 100 != 2:
		raise Exception('{} {}'.format(res.status, res.content['message']))
	return res.content

if __name__ == "__main__":
    for i in range(10):
        print "Step: ", i
        main()
