import dnf
import hawkey

repos = {
    'rawhide': 'https://mirrors.fedoraproject.org/metalink?repo=rawhide&arch=$basearch',
    'rawhide-source': 'https://mirrors.fedoraproject.org/metalink?repo=rawhide-source&arch=$basearch',
    # 'rawhide-modular': 'https://mirrors.fedoraproject.org/metalink?repo=rawhide-modular&arch=$basearch',
    # 'rawhide-modular-source': 'https://mirrors.fedoraproject.org/metalink?repo=rawhide-modular-source&arch=$basearch',
}

base = dnf.Base()
base.conf.cachedir = '/tmp/dnf'
base.conf.releasever = 'rawhide'
base.conf.module_platform_id = 'platform:f32'
base.conf.module_hotfixes = True
base.conf.prepend_installroot = '/tmp/dnf'
base.conf.substitutions['releasever'] = 'rawhide'
base.conf.substitutions['basearch'] = 'x86_64'

for repo in base.repos.all():
    repo.disable()

for repoid in repos:
    repo = dnf.repo.Repo(repoid, parent_conf=base.conf)
    if 'metalink' in repos[repoid]:
        repo.metalink = repos[repoid]
    else:
        repo.baseurl = repos[repoid]

    for metadata_type in ('primary', 'filelists', 'other', 'primary_db', 'filelists_db', 'other_db', 'group'):
        repo.add_metadata_type_to_download(metadata_type)

    repo.load_metadata_other = True
    repo.load()
    repo.enable()
    base.repos.add(repo)

base.fill_sack(load_system_repo=False)

if 'rawhide-modular' not in repos:
    base.sack.set_module_excludes([])

def get_pkg(base, package, arches=('x86_64', 'noarch'), repo_names=repos.keys()):
    """
    Do the hard work of resolving package to a hawkey.Package object, whether
    it is a name, a Reldep, or a hawkey.Package.
    """
    pkg = None
    if isinstance(package, str):
        pkg_list: list = None
        for repo_name in repo_names:
            for arch in arches:
                pkg_list = list(base.sack.query().filter(name=package, arch=arch, reponame=repo_name))
                if pkg_list:
                    break
            if pkg_list:
                break

        if not pkg_list or len(pkg_list) > 1:
            raise ValueError(f"Unable to uniquely resolve by name: {package} | {pkg_list} | {arches} | {repo_names}")

        pkg = pkg_list[0]
    elif isinstance(package, hawkey.Reldep):
        pkg_list: list = None
        for repo_name in repo_names:
            for arch in arches:
                pkg_list = list(base.sack.query().filter(provides=package, arch=arch, reponame=repo_name))
                if pkg_list:
                    for _pkg_ in pkg_list:
                        # If we have an exact match, choose that one above all
                        # others.
                        if _pkg_.name == str(package):
                            pkg_list = [_pkg_]
                            break
                    break
            if pkg_list:
                break

        if not pkg_list:
            raise ValueError(f"Unable to resolve by Reldep: {package} | {pkg_list} | {arches} | {repo_names}")

        pkg = pkg_list[0]
    else:
        pkg = package

    return pkg

def get_source_pkg(base, package):
    if isinstance(package, hawkey.Package):
        return get_pkg(base, package.source_name, arches=('src',))

    return get_pkg(base, package, arches=('src',))

def get_requires(base, package):
    pkg = get_pkg(base, package)

    result = set()
    for requires in set(pkg.requires):
        try:
            result.add(get_pkg(base, requires))
        except ValueError:
            print(f"Unable to resolve dependency: {str(requires)} of {str(package)}")

    return result

def get_build_requires(base, package):
    pkg = get_source_pkg(base, package)

    result = set()
    for requires in set(pkg.requires):
        try:
            result.add(get_pkg(base, requires))
        except ValueError:
            print(f"Unable to resolve dependency: {str(requires)} of {str(package)}")

    return result

def get_all_requires(base, package, depth=10):
    pkg = get_pkg(base, package)
    src_pkg = get_source_pkg(base, package)

    result = set()
    recent = set()
    recent.add(pkg)

    for i in range(0, depth):
        next_recent = set()
        for pkg in recent:
            for req in get_requires(base, pkg):
                next_recent.add(req)
            for req in get_build_requires(base, pkg):
                next_recent.add(req)
        next_recent.difference_update(result)
        next_recent.difference_update(recent)
        result.update(next_recent)
        recent = next_recent

    return result
