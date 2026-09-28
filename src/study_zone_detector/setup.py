from setuptools import find_packages, setup

package_name = 'study_zone_detector'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Juan Yin',
    maintainer_email='j9yin@ucsd.edu',
    description='Study Buddy Pupper: study-zone presence detection node.',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'detector = study_zone_detector.presence_detector:main',
            'phone = study_zone_detector.phone_detector:main',   # color-card phone-distraction
        ],
    },
)
