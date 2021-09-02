#!/usr/bin/python3

# This code is revised from DRiLLs paper baseline result
# Change environment from 7nm ASICs mapping to FPGA mapping

import yaml
import os
import subprocess
import sys
import timeit
import re
from joblib import Parallel, delayed

data_file = sys.argv[1]

with open(data_file, 'r') as f:
    options = yaml.load(f)

start = timeit.default_timer()

optimizations = options['optimizations']
iterations = options['iterations']
current_design_file = options['design_file']
#library_file = options['mapping']['library_file']
clock_period = options['mapping']['clock_period']
post_mapping_optimizations = options['post_mapping_commands']

# Create directory if not exists
if not os.path.exists(options['output_dir']):
    os.makedirs(options['output_dir'])

def extract_results(stats):
    """
    extracts LUTCount and level from the printed stats on stdout
    """
    line = stats.decode("utf-8").split('\n')[-2].split(':')[-1].strip()

    ob = re.search(r'lev *= *[1-9]+.?[0-9]*', line)
    level = float(ob.group().split('=')[1].strip())
    ob = re.search(r'nd *= *[1-9]+.?[0-9]*', line)
    LUTCount = float(ob.group().split('=')[1].strip())
    print("level is ", level, "LUTCount is ", LUTCount)
    return level, LUTCount

def run_optimization(output_dir, optimization, design_file):
    """
    returns new_design_file, level, LUTCount
    """
    output_dir = output_dir.replace(' ', '_')
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    output_design_file = output_dir + '/design.blif'

    #abc_command = 'read ' + library + '; '
    abc_command = 'read ' + design_file + '; '
    abc_command += 'strash; '
    abc_command += optimization + '; '
    abc_command += 'if -K 6;'
    abc_command += 'write ' + output_design_file + '; '
    abc_command += 'print_stats; '
    #abc_command += 'map -D ' + str(clock_period) + '; '
    #abc_command += 'topo; stime; '

    proc = subprocess.check_output(['yosys-abc','-c', abc_command])
    d, a = extract_results(proc)
    return output_design_file, d, a

def save_optimization_step(iteration, optimization, level, LUTCount):
    """
    saves the winning optimization to a csv file
    """
    with open(os.path.join(options['output_dir'], 'results.csv'), 'a') as f:
        data_point = str(iteration) + ', ' + str(optimization) + ', '
        data_point += str(level) + ', ' + str(LUTCount) + '\n'
        f.write(data_point)

def log(message=''):
    print(message)
    with open(os.path.join(options['output_dir'], 'greedy.log'), 'a') as f:
        f.write(message + '\n')

def run_post_mapping(output_dir, optimization, design_file):
    """
    returns new_design_file, level, LUTCount
    """
    output_dir = output_dir.replace(' ', '_')
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    output_design_file = output_dir + '/design.blif'

    #abc_command = 'read ' + library + '; '
    abc_command = 'read ' + design_file + '; '
    abc_command += 'strash; '
    abc_command += 'map -D ' + str(clock_period) + '; '
    abc_command += optimization + ';'
    abc_command += 'if -K 6;'
    abc_command += 'write ' + output_design_file + '; '
    abc_command += 'print_stats; '
    proc = subprocess.check_output(['yosys-abc','-c', abc_command])
    d, a = extract_results(proc)
    return output_design_file, d, a

def run_thread(iteration_dir, design_file, opt):
    opt_dir = os.path.join(iteration_dir, opt)
    opt_file, level, LUTCount = run_optimization(opt_dir, opt,
                                                     design_file)
    log('Optimization: ' + opt + ' -> level: ' + str(level) + ', LUTCount: ' + str(LUTCount))
    return (opt, opt_file, level, LUTCount)

def run_thread_post_mapping(iteration_dir, design_file, opt):
    opt_dir = os.path.join(iteration_dir, opt)
    opt_file, level, LUTCount = run_post_mapping(opt_dir, opt,
                                                     design_file)
    log('Optimization: ' + opt + ' -> level: ' + str(level) + ', LUTCount: ' + str(LUTCount))
    return (opt, opt_file, level, LUTCount)

# main optimizing iteration
previous_LUTCount = None
for i in range(iterations):
    # log
    log('Iteration: ' + str(i+1))
    log('-------------')

    # create a directory for this iteration
    iteration_dir = os.path.join(options['output_dir'], str(i))
    if not os.path.exists(iteration_dir):
        os.makedirs(iteration_dir)

    # in parallel, run ABC on each of the optimizations we have
    results = Parallel(n_jobs=len(optimizations))(delayed(run_thread)(iteration_dir, current_design_file, opt) for opt in optimizations)

    # get the minimum result of all threads
    best_thread = min(results, key = lambda t: t[3])  # getting minimum for level (index=2) or LUTCount (index=3)

    # hold the best result in variables
    best_optimization = best_thread[0]
    best_optimization_file = best_thread[1]
    best_level = best_thread[2]
    best_LUTCount = best_thread[3]



    if best_LUTCount == previous_LUTCount:
        # break for now
        log('Looks like the best LUTCount is exactly the same as last iteration!')
        log('Continue anyway ..')
        log('Choosing Optimization: ' + best_optimization + ' -> level: ' + str(best_level) + ', LUTCount: ' + str(best_LUTCount))
        save_optimization_step(i, best_optimization, best_level, best_LUTCount)

        log()

        # update design file for the next iteration
        current_design_file = best_optimization_file
        log('================')
        log()
        continue

        log()
        log('Looks like the best LUTCount is exactly the same as last iteration!')
        log('Performing post mapping optimizations ..')
        # run post mapping optimization
        results = Parallel(n_jobs=len(post_mapping_optimizations))(delayed(run_thread_post_mapping)(iteration_dir, current_design_file, opt) for opt in post_mapping_optimizations)

        # get the minimum result of all threads
        best_thread = min(results, key = lambda t: t[3])  # getting minimum for level (index=2) or LUTCount (index=3)

        # hold the best result in variables
        best_optimization = best_thread[0]
        best_optimization_file = best_thread[1]
        best_level = best_thread[2]
        best_LUTCount = best_thread[3]
        previous_LUTCount = None
    else:
        previous_LUTCount = best_LUTCount

    # save results
    log()
    log('Choosing Optimization: ' + best_optimization + ' -> level: ' + str(best_level) + ', LUTCount: ' + str(best_LUTCount))
    save_optimization_step(i, best_optimization, best_level, best_LUTCount)

    # update design file for the next iteration
    current_design_file = best_optimization_file
    log('================')
    log()

stop = timeit.default_timer()

log('Total Optimization Time: ' + str(stop - start))
