from distutils.core import setup

setup(
    name='sample_editor',
    version='0.1',
    description='Number of tools for sample cutting, render and anylyzing'
    'in flexible GUI wrapping. Requires REAPER.',
    author='Levitanus',
    author_email='pianoist@ya.ru',
    entry_points={
        'console_scripts': ['sample_editor = sample_editor.__main__:main']
    },
    packages=['sample_editor'],  # same as name
    package_data={'sample_editor': ['py.typed']},
    install_requires=['aenum', 'librosa', 'reapy-boost', 'PySimpleGUI'],
)
