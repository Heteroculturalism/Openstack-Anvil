#!/bin/bash

# This script cleans up the system as part of a nova uninstall
#
# It is best effort!
# 
# There are other scripts in tools/ that might be able to recover it better (but are distro specific)

if [[ $EUID -ne 0 ]]; then
   echo "This script must be run as root!" 1>&2
   exit 1
fi

set +o errexit
set -x

# Set up some good defaults
ENABLED_SERVICES=${ENABLED_SERVICES:-net,vol}
VOLUME_NAME_PREFIX=${VOLUME_NAME_PREFIX:-volume-}

# Clean off networking
if [[ "$ENABLED_SERVICES" =~ "net" ]]; then

    # Ignore any errors from shutting down dnsmasq
    service dnsmasq stop

    # The above doesn't always work so this way will just incase
    for pid in `ps -elf | grep -i dnsmasq | grep nova | perl -le 'while (<>) { my $pid = (split /\s+/)[3]; print $pid; }'`
    do
        echo "Killing leftover nova dnsmasq process with process id $pid"
        kill -9 $pid
    done

    # Delete rules
    iptables -S -v | sed "s/-c [0-9]* [0-9]* //g" | grep "nova" | grep "\-A" |  sed "s/-A/-D/g" | awk '{print "iptables",$0}' | bash
    
    # Delete nat rules
    iptables -S -v -t nat | sed "s/-c [0-9]* [0-9]* //g" | grep "nova" |  grep "\-A" | sed "s/-A/-D/g" | awk '{print "iptables -t nat",$0}' | bash
    
    # Delete chains
    iptables -S -v | sed "s/-c [0-9]* [0-9]* //g" | grep "nova" | grep "\-N" |  sed "s/-N/-X/g" | awk '{print "iptables",$0}' | bash
    
    # Delete nat chains
    iptables -S -v -t nat | sed "s/-c [0-9]* [0-9]* //g" | grep "nova" |  grep "\-N" | sed "s/-N/-X/g" | awk '{print "iptables -t nat",$0}' | bash

fi

# Clean off volumes
if [[ "$ENABLED_SERVICES" =~ "vol" ]]; then

    # Logout and delete iscsi sessions
    iscsiadm --mode node | grep $VOLUME_NAME_PREFIX | cut -d " " -f2 | xargs iscsiadm --mode node --logout
    iscsiadm --mode node | grep $VOLUME_NAME_PREFIX | cut -d " " -f2 | iscsiadm --mode node --op delete

fi

exit 0
