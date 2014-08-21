import time, datetime
#time.strftime("%Y-%m-%d %H:%M:%S")
#datetime.strptime("2010-06-04 21:08:12", "%Y-%m-%d %H:%M:%S")

class PackageError(Exception):
    pass

class PackageNotFound(Exception):
    pass

class PackageInconsistent(Exception):
    pass

class PackageSupportError(Exception):
    pass

