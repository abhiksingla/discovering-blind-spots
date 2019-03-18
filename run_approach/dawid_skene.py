"""
Copyright (C) 2014 Dallas Card

Permission is hereby granted, free of charge, to any person obtaining a copy of this
software and associated documentation files (the "Software"), to deal in the Software
without restriction, including without limitation the rights to use, copy, modify, merge,
publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons
 to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or
substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR
PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE
FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
DEALINGS IN THE SOFTWARE.


Description:
Given unreliable observations of patient classes by multiple observers,
determine the most likely true class for each patient, class marginals,
and  individual error rates for each observer, using Expectation Maximization


References:
( Dawid and Skene (1979). Maximum Likelihood Estimation of Observer
Error-Rates Using the EM Algorithm. Journal of the Royal Statistical Society.
Series C (Applied Statistics), Vol. 28, No. 1, pp. 20-28. 
"""

import numpy as np
import sys
import collections
from review import Review
import test_approach
import pdb


"""
Function: main()
    Run the EM estimator on the data from the Dawid-Skene paper
"""

def main(input_filename, output_filename, label_type_str):
    for i in test_approach.all_label_types:
        name, properties = i
        if name == label_type_str:
            label_type = i

    # load the data
    responses, review_counts, classes = read_input_data(input_filename)

    # run EM
    return run(responses, review_counts, classes, output_filename, label_type)


"""
Read input data from file.
Example data looks like:
{
    1: {1:[0,1,1,0]},
    2: {1:[1,1,1,1,1,1]}
}
Each key in the dictionary is a state.
The index within this specifies the observer (in this case, we only have one), and this points to a list of observations. In our case, the observations are binary labels.
"""
def read_input_data(filename):
    lines = [line.rstrip('\n') for line in open(filename)]
    data = collections.OrderedDict()
    classes = [0,1]

    review_counts = np.zeros(len(classes))

    for line in lines:
        values = line.split("=")
        x_i = values[0][1:-1].split(",")
        x_i = tuple([int(x.strip()) for x in x_i])
        if x_i not in data:
            data[x_i] = {1:[]}
        labels = values[1][1:-1].split(",") # List of labels
        for label_str in labels:
            label_values = label_str[1:-1].split(";")
            class_label = int(label_values[0])
            truth_label = label_values[1]
            if truth_label == "t":
                review_counts[class_label] += 1
            label = (class_label, truth_label)
            data[x_i][1].append(label)

    return data, review_counts, classes


"""
Function: dawid_skene()
    Run the Dawid-Skene estimator on response data
Input:
    responses: a dictionary object of responses:
        {patients: {observers: [labels]}}
    tol: tolerance required for convergence of EM
    max_iter: maximum number of iterations of EM
""" 
def run(responses, review_counts, classes, output_filename, label_type, tol=0.00001, max_iter=100, init='average'):
    # convert responses to counts
    (patients, observers, classes, counts, gold_data) = responses_to_counts(responses, classes)
    print("num Patients:", len(patients))
    print("Observers:", observers)
    print("Classes:", classes)
    
    # initialize
    iteration = 0
    converged = False
    old_class_marginals = None
    old_error_rates = None
    patient_classes, reviewed_blindspots = initialize(counts, gold_data, label_type)

    print("Iteration\tlog-likelihood\tdelta-CM\tdelta-ER")

    while not converged:     
        iteration += 1
        
        # M-step
        (class_marginals, error_rates) = m_step(counts, review_counts, gold_data, patient_classes, label_type, iteration)

        [nPatients, nObservers, nClasses] = np.shape(counts)

        # E-step
        patient_classes = e_step(counts, gold_data, class_marginals, error_rates, label_type)

        # check likelihood
        log_L = calc_likelihood(counts, class_marginals, error_rates)
        
        # check for convergence
        if old_class_marginals is not None:
            class_marginals_diff = np.sum(np.abs(class_marginals - old_class_marginals))
            error_rates_diff = np.sum(np.abs(error_rates - old_error_rates))
            print(iteration ,'\t', log_L, '\t%.6f\t%.6f' % (class_marginals_diff, error_rates_diff))
            if (class_marginals_diff < tol and error_rates_diff < tol) or iteration > max_iter:
                converged = True
        else:
            print(iteration ,'\t', log_L)
    
        # update current values
        old_class_marginals = class_marginals
        old_error_rates = error_rates
                
    # Print final results
    np.set_printoptions(precision=2, suppress=True)
    print("Class marginals")
    print(class_marginals)
    print("Error rates")
    print(error_rates)

    print("Incidence-of-error rates")
    [nPatients, nObservers, nClasses] = np.shape(counts)
    for k in range(nObservers):
        print(class_marginals * error_rates[k,:,:])

    np.set_printoptions(precision=4, suppress=True)

    write_to_file(nPatients, patients, patient_classes, output_filename)
    return patient_classes, class_marginals, error_rates


"""
For each state, write the majority label to a file along with the corresponding weight learned from Dawid-Skene.
"""
def write_to_file(nPatients, patients, patient_classes, output_filename):
    labels = []
    weights = []
    for i in range(nPatients):
        best_label = np.argmax(patient_classes[i,:])
        labels.append(best_label)
        weights.append(patient_classes[i,best_label])
    with open(output_filename, 'w') as f:
        for i in range(nPatients):
            f.write(""+str(list(patients[i]))+","+str(labels[i])+","+str(weights[i])+"\n")


"""
Function: responses_to_counts()
    Convert a matrix of annotations to count data
Inputs:
    responses: dictionary of responses {patient:{observers:[responses]}}
Return:
    patients: list of patients
    observers: list of observers
    classes: list of possible patient classes
    counts: 3d array of counts: [patients x observers x classes]
""" 
def responses_to_counts(responses, classes):
    patients = list(responses.keys())
    # patients.sort()
    nPatients = len(patients)
        
    # determine the observers and classes
    observers = set()

    for i in patients:
        i_observers = responses[i].keys()
        for k in i_observers:
            if k not in observers:
                observers.add(k)
            ik_responses = responses[i][k]
            class_labels = [x[0] for x in ik_responses]
            truth_labels = [x[1] for x in ik_responses]

    # classes.sort()
    nClasses = len(classes)
        
    observers = list(observers)
    # observers.sort()
    nObservers = len(observers)

    # create a 3d array to hold counts
    counts = np.zeros([nPatients, nObservers, nClasses])
    gold_data = np.zeros([nPatients])
    
    # convert responses to counts
    for patient in patients:
        i = patients.index(patient)
        for observer in responses[patient].keys():
            k = observers.index(observer)
            for response in responses[patient][observer]:
                class_label, truth_label = response
                j = classes.index(class_label)
                counts[i,k,j] += 1
                if class_label == 1 and truth_label == 't':
                    gold_data[i] = 1

    return (patients, observers, classes, counts, gold_data)


"""
Function: initialize()
    Get initial estimates for the true patient classes using counts
    see equation 3.1 in Dawid-Skene (1979)
Input:
    counts: counts of the number of times each response was received 
        by each observer from each patient: [patients x observers x classes] 
Returns:
    patient_classes: matrix of estimates of true patient classes:
        [patients x responses]
"""  
def initialize(counts, gold_data, label_type):
    [nPatients, nObservers, nClasses] = np.shape(counts)
    # sum over observers
    response_sums = np.sum(counts,1)
    
    reviewed_blindspots = []

    # create an empty array
    patient_classes = np.zeros([nPatients, nClasses])
    # for each patient, take the average number of observations in each class
    for p in range(nPatients):
        if (label_type[1]["AM_noise"] == 0 and counts[p,:,1] > 0) or (label_type[1]["AM_noise"] == 2 and gold_data[p] > 0):
            reviewed_blindspots.append(p)
            patient_classes[p,1] = 1
            patient_classes[p,0] = 0
            continue

        p_sum = np.sum(response_sums[p,:],dtype=float)
        if p_sum > 0:
            patient_classes[p,:] = response_sums[p,:] / p_sum

    return patient_classes, reviewed_blindspots


"""
Function: m_step()
    Get estimates for the prior class probabilities (p_j) and the error
    rates (pi_jkl) using MLE with current estimates of true patient classes
    See equations 2.3 and 2.4 in Dawid-Skene (1979)
Input: 
    counts: Array of how many times each response was received
        by each observer from each patient
    patient_classes: Matrix of current assignments of patients to classes
Returns:
    p_j: class marginals [classes]
    pi_kjl: error rates - the probability of observer k receiving
        response l from a patient in class j [observers, classes, classes]
"""
def m_step(counts, review_counts, gold_data, patient_classes, label_type, iteration):
    [nPatients, nObservers, nClasses] = np.shape(counts)

    # compute class marginals
    class_marginals = np.sum(patient_classes,0)/float(nPatients)

    # compute error rates
    error_rates = np.zeros([nObservers, nClasses, nClasses])
    other_error_rates = np.zeros([nObservers, nClasses, nClasses])
    for k in range(nObservers):
        for j in range(nClasses):
            if (label_type[1]["AM_noise"] == 0 and j == 0):
                error_rates[k,j,0] = 1
                error_rates[k,j,1] = 0
                continue

            for l in range(nClasses):
                error_rates[k, j, l] = np.dot(patient_classes[:,j], counts[:,k,l])
            
            # normalize by summing over all observation classes
            sum_over_responses = np.sum(error_rates[k,j,:])
            if sum_over_responses > 0:
                error_rates[k,j,:] = error_rates[k,j,:]/float(sum_over_responses)  
    return (class_marginals, error_rates)


""" 
Function: e_step()
    Determine the probability of each patient belonging to each class,
    given current ML estimates of the parameters from the M-step
    See equation 2.5 in Dawid-Skene (1979)
Inputs:
    counts: Array of how many times each response was received
        by each observer from each patient
    class_marginals: probability of a random patient belonging to each class
    error_rates: probability of observer k assigning a patient in class j 
        to class l [observers, classes, classes]
Returns:
    patient_classes: Soft assignments of patients to classes
        [patients x classes]
"""      
def e_step(counts, gold_data, class_marginals, error_rates, label_type):
    [nPatients, nObservers, nClasses] = np.shape(counts)

    patient_classes = np.zeros([nPatients, nClasses])    

    for i in range(nPatients):
        for j in range(nClasses):
            if (label_type[1]["AM_noise"] == 0 and counts[i,:,1] > 0) or (label_type[1]["AM_noise"] == 2 and gold_data[i] > 0):
                patient_classes[i,1] = 1
                patient_classes[i,0] = 0
                continue

            estimate = class_marginals[j]
            estimate *= np.prod(np.power(error_rates[:,j,:], counts[i,:,:]))
            patient_classes[i,j] = estimate

        # normalize error rates by dividing by the sum over all observation classes
        patient_sum = np.sum(patient_classes[i,:])
        if patient_sum > 0:
            patient_classes[i,:] = patient_classes[i,:]/float(patient_sum)
    
    return patient_classes


"""
Function: calc_likelihood()
    Calculate the likelihood given the current parameter estimates
    This should go up monotonically as EM proceeds
    See equation 2.7 in Dawid-Skene (1979)
Inputs:
    counts: Array of how many times each response was received
        by each observer from each patient
    class_marginals: probability of a random patient belonging to each class
    error_rates: probability of observer k assigning a patient in class j 
        to class l [observers, classes, classes]
Returns:
    Likelihood given current parameter estimates
"""  
def calc_likelihood(counts, class_marginals, error_rates):
    [nPatients, nObservers, nClasses] = np.shape(counts)
    log_L = 0.0
    
    for i in range(nPatients):
        patient_likelihood = 0.0
        for j in range(nClasses):
        
            class_prior = class_marginals[j]
            patient_class_likelihood = np.prod(np.power(error_rates[:,j,:], counts[i,:,:]))
            patient_class_posterior = class_prior * patient_class_likelihood
            patient_likelihood += patient_class_posterior
                              
        temp = log_L + np.log(patient_likelihood)
        
        if np.isnan(temp) or np.isinf(temp):
            print(i, log_L, np.log(patient_likelihood), temp)
            sys.exit()

        log_L = temp
        
    return log_L


"""
Function: random_initialization()
    Alternative initialization # 1
    Similar to initialize() above, except choose one initial class for each
    patient, weighted in proportion to the counts
Input:
    counts: counts of the number of times each response was received 
        by each observer from each patient: [patients x observers x classes] 
Returns:
    patient_classes: matrix of estimates of true patient classes:
        [patients x responses]
"""  
def random_initialization(counts):
    [nPatients, nObservers, nClasses] = np.shape(counts)
    
    response_sums = np.sum(counts,1)
    
    # create an empty array
    patient_classes = np.zeros([nPatients, nClasses])
    
    # for each patient, choose a random initial class, weighted in proportion
    # to the counts from all observers
    for p in range(nPatients):
        average = response_sums[p,:] / np.sum(response_sums[p,:],dtype=float)
        patient_classes[p,np.random.choice(np.arange(nClasses), p=average)] = 1
        
    return patient_classes


"""
Function: majority_voting()
    Alternative initialization # 2
    An alternative way to initialize assignment of patients to classes 
    i.e Get initial estimates for the true patient classes using majority voting
    This is not in the original paper, but could be considered
Input:
    counts: Counts of the number of times each response was received 
        by each observer from each patient: [patients x observers x classes] 
Returns:
    patient_classes: matrix of initial estimates of true patient classes:
        [patients x responses]
"""  
def majority_voting(counts):
    [nPatients, nObservers, nClasses] = np.shape(counts)
    # sum over observers
    response_sums = np.sum(counts,1)
    
    # create an empty array
    patient_classes = np.zeros([nPatients, nClasses])
    
    # take the most frequent class for each patient 
    for p in range(nPatients):        
        indices = np.argwhere(response_sums[p,:] == np.max(response_sums[p,:]))
        # in the case of ties, take the lowest valued label (could be randomized)        
        patient_classes[p, np.min(indices)] = 1
        
    return patient_classes


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], sys.argv[3])