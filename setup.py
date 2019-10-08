from distutils.core import setup

setup(
    name='sample_editor',
    version='1.0',
    description='A useful module',
    author='Man Foo',
    author_email='foomail@foo.com',
    packages=['sample_editor', 'sample_editor/sub_package'],  # same as name
    package_data={'sample_editor': ['py.typed']}
    # install_requires=['bar', 'greek'], #external packages as dependencies
)
