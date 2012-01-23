# vim: tabstop=4 shiftwidth=4 softtabstop=4

#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

from devstack import cfg
from devstack import date
from devstack import exceptions as excp
from devstack import log as logging
from devstack import settings
from devstack import shell as sh
from devstack import utils

from devstack.components import db
from devstack.components import glance
from devstack.components import horizon
from devstack.components import keystone
from devstack.components import keystone_client
from devstack.components import nova
from devstack.components import nova_client
from devstack.components import openstack_x
from devstack.components import quantum
from devstack.components import rabbit
from devstack.components import swift

from devstack.packaging import apt
from devstack.packaging import yum

LOG = logging.getLogger("devstack.progs.actions")

#this map controls which distro has
#which package management class
_PKGR_MAP = {
    settings.UBUNTU11: apt.AptPackager,
    settings.RHEL6: yum.YumPackager,
}

# This is used to map an action to a useful string for
# the welcome display
_WELCOME_MAP = {
    settings.INSTALL: "INSTALLER",
    settings.UNINSTALL: "UNINSTALLER",
    settings.START: "STARTER",
    settings.STOP: "STOPPER",
}

# This determines what classes to use to install/uninstall/...
_ACTION_CLASSES = {
    settings.INSTALL: {
        settings.NOVA: nova.NovaInstaller,
        settings.GLANCE: glance.GlanceInstaller,
        settings.QUANTUM: quantum.QuantumInstaller,
        settings.SWIFT: swift.SwiftInstaller,
        settings.HORIZON: horizon.HorizonInstaller,
        settings.KEYSTONE: keystone.KeystoneInstaller,
        settings.DB: db.DBInstaller,
        settings.RABBIT: rabbit.RabbitInstaller,
        settings.KEYSTONE_CLIENT: keystone_client.KeyStoneClientInstaller,
        settings.NOVA_CLIENT: nova_client.NovaClientInstaller,
        settings.OPENSTACK_X: openstack_x.OpenstackXInstaller,
    },
    settings.UNINSTALL: {
        settings.NOVA: nova.NovaUninstaller,
        settings.GLANCE: glance.GlanceUninstaller,
        settings.QUANTUM: quantum.QuantumUninstaller,
        settings.SWIFT: swift.SwiftUninstaller,
        settings.HORIZON: horizon.HorizonUninstaller,
        settings.KEYSTONE: keystone.KeystoneUninstaller,
        settings.DB: db.DBUninstaller,
        settings.RABBIT: rabbit.RabbitUninstaller,
        settings.KEYSTONE_CLIENT: keystone_client.KeyStoneClientUninstaller,
        settings.NOVA_CLIENT: nova_client.NovaClientUninstaller,
        settings.OPENSTACK_X: openstack_x.OpenstackXUninstaller,
    },
    settings.START: {
        settings.NOVA: nova.NovaRuntime,
        settings.GLANCE: glance.GlanceRuntime,
        settings.QUANTUM: quantum.QuantumRuntime,
        settings.SWIFT: swift.SwiftRuntime,
        settings.HORIZON: horizon.HorizonRuntime,
        settings.KEYSTONE: keystone.KeystoneRuntime,
        settings.DB: db.DBRuntime,
        settings.RABBIT: rabbit.RabbitRuntime,
        settings.KEYSTONE_CLIENT: keystone_client.KeyStoneClientRuntime,
        settings.NOVA_CLIENT: nova_client.NovaClientRuntime,
        settings.OPENSTACK_X: openstack_x.OpenstackXRuntime,
    },
    settings.STOP: {
        settings.NOVA: nova.NovaRuntime,
        settings.GLANCE: glance.GlanceRuntime,
        settings.QUANTUM: quantum.QuantumRuntime,
        settings.SWIFT: swift.SwiftRuntime,
        settings.HORIZON: horizon.HorizonRuntime,
        settings.KEYSTONE: keystone.KeystoneRuntime,
        settings.DB: db.DBRuntime,
        settings.RABBIT: rabbit.RabbitRuntime,
        settings.KEYSTONE_CLIENT: keystone_client.KeyStoneClientRuntime,
        settings.NOVA_CLIENT: nova_client.NovaClientRuntime,
        settings.OPENSTACK_X: openstack_x.OpenstackXRuntime,
    },
}


def _clean_action(action):
    if(action == None):
        return None
    action = action.strip().lower()
    if(not (action in settings.ACTIONS)):
        return None
    return action


def _get_pkg_manager(distro):
    cls = _PKGR_MAP.get(distro)
    return cls(distro)


def _get_action_cls(action_name, component_name):
    action_cls_map = _ACTION_CLASSES.get(action_name)
    if(not action_cls_map):
        return None
    return action_cls_map.get(component_name)


def _check_root(action, rootdir):
    if(rootdir == None or len(rootdir) == 0):
        return False
    if(action == settings.INSTALL):
        if(sh.isdir(rootdir)):
            dir_list = sh.listdir(rootdir)
            if(len(dir_list) > 0):
                LOG.error("Root directory [%s] already exists (and it's not empty)! "\
                          "Please remove it or uninstall components!" % (rootdir))
                return False
    return True


def _pre_run(action_name, **kargs):
    if(action_name == settings.INSTALL):
        root_dir = kargs.get("root_dir")
        if(root_dir):
            sh.mkdir(root_dir)


def _post_run(action_name, **kargs):
    if(action_name == settings.UNINSTALL):
        root_dir = kargs.get("root_dir")
        if(root_dir):
            sh.rmdir(root_dir)


def _print_cfgs(cfg, action):

    #this will make the items nice and pretty
    def item_format(k, v):
        return "\t%s=%s" % (str(k), str(v))

    def map_print(mp):
        for key in sorted(mp.keys()):
            value = mp.get(key)
            LOG.info(item_format(key, value))

    #now make it pretty
    passwords_gotten = cfg.pws
    full_cfgs = cfg.configs_fetched
    db_dsns = cfg.db_dsns
    if(len(passwords_gotten) or len(full_cfgs) or len(db_dsns)):
        LOG.info("After action (%s) your settings are:" % (action))
        if(len(passwords_gotten)):
            LOG.info("Passwords:")
            map_print(passwords_gotten)
        if(len(full_cfgs)):
            #TODO
            #better way to do this?? (ie a list difference?)
            filtered_mp = dict()
            for key in full_cfgs.keys():
                if(key in passwords_gotten):
                    continue
                filtered_mp[key] = full_cfgs.get(key)
            if(len(filtered_mp)):
                LOG.info("Configs:")
                map_print(filtered_mp)
        if(len(db_dsns)):
            LOG.info("Data source names:")
            map_print(db_dsns)


def _install(component_name, instance):
    LOG.info("Downloading %s." % (component_name))
    am_downloaded = instance.download()
    LOG.info("Performed %s downloads." % (am_downloaded))
    LOG.info("Configuring %s." % (component_name))
    am_configured = instance.configure()
    LOG.info("Configured %s items." % (am_configured))
    LOG.info("Pre-installing %s." % (component_name))
    instance.pre_install()
    LOG.info("Installing %s." % (component_name))
    instance.install()
    LOG.info("Post-installing %s." % (component_name))
    trace = instance.post_install()
    if(trace):
        LOG.info("Finished install of %s - check %s for traces of what happened." % (component_name, trace))
    else:
        LOG.info("Finished install of %s" % (component_name))
    return trace


def _stop(component_name, instance, skip_notrace):
    try:
        LOG.info("Stopping %s." % (component_name))
        stop_amount = instance.stop()
        LOG.info("Stopped %s items." % (stop_amount))
        LOG.info("Finished stop of %s" % (component_name))
    except excp.NoTraceException, e:
        if(skip_notrace):
            LOG.info("Passing on stopping %s since no trace file was found." % (component_name))
        else:
            raise


def _start(component_name, instance):
    LOG.info("Pre-starting %s." % (component_name))
    instance.pre_start()
    LOG.info("Starting %s." % (component_name))
    start_info = instance.start()
    LOG.info("Post-starting %s." % (component_name))
    instance.post_start()
    if(type(start_info) == list):
        LOG.info("Check [%s] for traces of what happened." % (", ".join(start_info)))
    elif(type(start_info) == int):
        LOG.info("Started %s applications." % (start_info))
        start_info = None
    LOG.info("Finished start of %s." % (component_name))
    return start_info


def _uninstall(component_name, instance, skip_notrace):
    try:
        LOG.info("Unconfiguring %s." % (component_name))
        instance.unconfigure()
        LOG.info("Uninstalling %s." % (component_name))
        instance.uninstall()
    except excp.NoTraceException, e:
        if(skip_notrace):
            LOG.info("Passing on uninstalling %s since no trace file was found." % (component_name))
        else:
            raise


def _get_config():
    cfg_fn = sh.canon_path(settings.STACK_CONFIG_LOCATION)
    LOG.info("Loading config from [%s]" % (cfg_fn))
    config_instance = cfg.EnvConfigParser()
    config_instance.read(cfg_fn)
    return config_instance


def _run_components(action_name, component_order, components_info, distro, root_dir, program_args):
    LOG.info("Will %s [%s] (in that order) using root directory \"%s\"" % (action_name, ", ".join(component_order), root_dir))
    pkg_manager = _get_pkg_manager(distro)
    config = _get_config()
    results = list()
    #this key list may be different than the order due to reference components
    active_components = components_info.keys()
    #run anything before it gets going...
    _pre_run(action_name, root_dir=root_dir, pkg=pkg_manager, cfg=config)
    for component in component_order:
        action_cls = _get_action_cls(action_name, component)
        instance = action_cls(components=set(active_components),
                            distro=distro,
                            pkg=pkg_manager,
                            cfg=config,
                            root=root_dir,
                            component_opts=components_info.get(component, list()))
        #activate the correct function for the given action
        if(action_name == settings.INSTALL):
            install_result = _install(component, instance)
            if install_result:
                if type(install_result) == list:
                    results += install_result
                else:
                    results.append(str(install_result))
        elif(action_name == settings.STOP):
            _stop(component, instance, program_args.get('force', False))
        elif(action_name == settings.START):
            start_result = _start(component, instance)
            if start_result:
                if type(start_result) == list:
                    results += start_result
                else:
                    results.append(str(start_result))
        elif(action_name == settings.UNINSTALL):
            _uninstall(component, instance, program_args.get('force', False))
        else:
            #TODO throw?
            pass
    #display any configs touched...
    _print_cfgs(config, action_name)
    #any post run actions go now
    _post_run(action_name, root_dir=root_dir, pkg=pkg_manager, cfg=config)
    return results


def _run_action(args):
    components = settings.parse_components(args.pop("components"))
    if(len(components) == 0):
        LOG.error("No components specified!")
        return False
    action = _clean_action(args.pop("action"))
    if(not action):
        LOG.error("No valid action specified!")
        return False
    rootdir = args.pop("dir")
    if(not _check_root(action, rootdir)):
        LOG.error("No valid root directory specified!")
        return False
    #ensure os/distro is known
    (distro, platform) = utils.determine_distro()
    if(distro == None):
        LOG.error("Unsupported platform: %s" % (platform))
        return False
    #start it
    utils.welcome(_WELCOME_MAP.get(action))
    #need to figure out dependencies for components (if any)
    ignore_deps = args.pop('ignore_deps', False)
    if(not ignore_deps):
        new_components = settings.resolve_dependencies(components.keys())
        component_diff = new_components.difference(components.keys())
        if(len(component_diff)):
            LOG.info("Having to activate dependent components: [%s]" % (", ".join(component_diff)))
            for new_component in component_diff:
                components[new_component] = list()
    #get the right component order (by priority)
    component_order = settings.prioritize_components(components.keys())
    #add in any that will just be referenced but which will not actually do anything (ie the action will not be applied to these)
    ref_components = settings.parse_components(args.pop("ref_components"))
    for c in ref_components.keys():
        if(c not in components):
            components[c] = ref_components.get(c)
    #now do it!
    LOG.info("Starting action [%s] on %s for distro [%s]" % (action, date.rcf8222date(), distro))
    results = _run_components(action, component_order, components, distro, rootdir, args)
    LOG.info("Finished action [%s] on %s" % (action, date.rcf8222date()))
    if(results):
        LOG.info('Check [%s] for traces of what happened.' % ", ".join(results))
    return True


def run(args):
    return _run_action(args)
