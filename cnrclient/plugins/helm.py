from __future__ import print_function
import os
import sys
import subprocess

import yaml

from cnrclient.client import CnrClient
from cnrclient.utils import mkdir_p, parse_package_name
from cnrclient.pack import CnrPackage

DEFAULT_CHARTS = "appr_charts"


def parse_version(version):
    """
     Converts a version string to a dict with following rules:
       if string starts with ':' it is a channel
       if string starts with 'sha256' it is a digest
       else it is a release
    """
    if version[0] == ':' or version.startswith('channel:'):
        parts = {'key': 'channel', 'value': version.split(':')[1]}
    elif version.startswith('sha256:'):
        parts = {'key': 'digest', 'value': version.split('sha256:')[1]}
    else:
        parts = {'key': 'version', 'value': version}

    return parts


class Helm(object):
    def __init__(self):
        pass

    def download_appr_deps(self, deps, dest=DEFAULT_CHARTS, tarball=False):
        """
            Creates a directory 'dep_charts' to download and extract all dependencies
            fetched from the app-registry server.
            returns a helm dependency list
        """
        mkdir_p(dest)
        helm_deps = {}
        for dep in deps:
            package_parts = parse_package_name(dep['name'])
            name = package_parts['package']

            vparts = parse_version(dep['version'])
            client = CnrClient(package_parts['host'])
            package_name = '%s/%s' % (package_parts['namespace'], name)

            pullpack = client.pull_json(package_name, version_parts=vparts, media_type='helm')
            package = CnrPackage(pullpack['blob'], b64_encoded=True)
            release = pullpack['release']
            packagepath = os.path.join(dest, package_parts['namespace'])
            print('Pulled package: %s (%s) \n -> %s' % (dep['name'], release, packagepath),
                  file=sys.stderr)
            if tarball:
                with open('%s-%s.tgz' % (name, release), 'wb') as tarfile:
                    tarfile.write(package.blob)
            package.extract(packagepath)

            helm_deps[name] = {
                'name': name,
                'version': release,
                'repository': 'file://%s/%s' % (packagepath, name)
            }
        return helm_deps

    def build_dep(self, dest=DEFAULT_CHARTS, overwrite=False):
        """
            Reads the dependencies from the requirements.yaml, downloads the packages and updates
            the requirements.yaml.
            Returns status
        """
        with open('requirements.yaml', 'rb') as requirefile:
            deps = yaml.safe_load(requirefile.read())
        helm_deps = {}
        if 'appr' in deps and deps['appr']:
            helm_deps = self.download_appr_deps(deps['appr'], dest)
            dict_deps = {dep['name']: dep for dep in deps['dependencies']}
            dict_deps.update(helm_deps)
            deps['dependencies'] = dict_deps.values()
            requirement_output = yaml.safe_dump(deps, default_flow_style=False)
            if overwrite:
                with open('requirements.yaml', 'wb') as requirefile:
                    requirefile.write(requirement_output)
                return 'Updated requirements.yaml'
            else:
                return requirement_output
        else:
            return "No appr-registries dependencies"

    def action(self, cmd, package_path, helm_opts=None):
        cmd = [cmd]
        if helm_opts:
            cmd = cmd + helm_opts
        cmd.append(package_path)
        return self._call(cmd)

    def _call(self, cmd):
        command = ['helm'] + cmd
        try:
            return subprocess.check_output(command, stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as exc:
            return exc.output
