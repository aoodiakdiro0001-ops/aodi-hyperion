#!/usr/bin/env python3
'''A deliberate vulnerability fixture — verifier heuristics must flag these (never execute in production).'''
import os, subprocess, pickle
def boom(user):
    os.system("cat " + user)
    subprocess.Popen(user, shell=True)
    return pickle.loads(user)
def leak():
    token = "ghp_supersecrettokenvalue1234"
    return eval(token)
