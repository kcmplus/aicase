"""Access logs retain path/status/timing, never OAuth query strings or referrers."""
access_log_format = '%(h)s %(t)s "%(m)s %(U)s %(H)s" %(s)s %(b)s %(L)s'
