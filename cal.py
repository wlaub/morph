import math


import numpy as np

import discorpy.losa.loadersaver as io
import discorpy.prep.preprocessing as prep
import discorpy.proc.processing as proc
import discorpy.post.postprocessing as post

import discorpy.prep.linepattern as lprep

file_path = "gridcal.jpg"
file_path = 'unwarp_test/inputs/triangles.png'
output_base = "cal_test"
num_coef = 5  # Number of polynomial coefficients
mat0 = io.load_image(file_path) # Load image
(height, width) = mat0.shape
slope_hor, dist_hor = lprep.calc_slope_distance_hor_lines(mat0, ratio=0.3, search_range=1)
slope_ver, dist_ver = lprep.calc_slope_distance_ver_lines(mat0, ratio=0.3, search_range=1)
print("    Horizontal slope: ", slope_hor, " Distance: ", dist_hor)
print("    Vertical slope: ", slope_ver, " Distance: ", dist_ver)

ah = math.atan(slope_hor)*180/math.pi
av = math.atan(slope_ver)*180/math.pi
print(ah, av)


exit(0)

# Initial parameters
file_path = "cal11.jpg"
output_base = "cal_test"
num_coef = 5  # Number of polynomial coefficients
mat0 = io.load_image(file_path) # Load image
(height, width) = mat0.shape

mat1 = prep.normalization_fft(mat0, sigma=20)
mat1=np.array(mat0)
io.save_image(output_base + "/image_normed.jpg", mat1)
threshold = prep.calculate_threshold(mat1, bgr="bright", snr=3.0)
print(threshold)
threshold = 128
mat1 = prep.binarization(mat1, ratio=0.3, thres=threshold)
io.save_image(output_base + "/image_binarized.jpg", mat1)
# Calculate the median dot size and distance between them.
(dot_size, dot_dist) = prep.calc_size_distance(mat1)
print(dot_size, dot_dist)
#dot_size, dot_dist = 451.0, 53.09686051731639
# Remove non-dot objects
mat1 = prep.select_dots_based_size(mat1, dot_size, ratio=0.3)
# Remove non-elliptical objects
mat1 = prep.select_dots_based_ratio(mat1, ratio=0.3)
io.save_image(output_base + "/image_cleaned.jpg", mat1)

# Calculate the slopes of horizontal lines and vertical lines.
hor_slope = prep.calc_hor_slope(mat1)
ver_slope = prep.calc_ver_slope(mat1)
print("Horizontal slope: {0}. Vertical slope: {1}".format(hor_slope, ver_slope))

# Group points into lines
list_hor_lines = prep.group_dots_hor_lines(mat1, hor_slope, dot_dist, ratio=0.3,
                                           num_dot_miss=10, accepted_ratio=0.65)
list_ver_lines = prep.group_dots_ver_lines(mat1, ver_slope, dot_dist, ratio=0.3,
                                           num_dot_miss=10, accepted_ratio=0.65)
# Remove outliers
list_hor_lines = prep.remove_residual_dots_hor(list_hor_lines, hor_slope,
                                               residual=2.0)
list_ver_lines = prep.remove_residual_dots_ver(list_ver_lines, ver_slope,
                                               residual=2.0)

# Save output for checking
io.save_plot_image(output_base + "/horizontal_lines.png", list_hor_lines,
                   height, width)
io.save_plot_image(output_base + "/vertical_lines.png", list_ver_lines,
                   height, width)
list_hor_data = post.calc_residual_hor(list_hor_lines, 0.0, 0.0)
list_ver_data = post.calc_residual_ver(list_ver_lines, 0.0, 0.0)
io.save_residual_plot(output_base + "/hor_residual_before_correction.png",
                      list_hor_data, height, width)
io.save_residual_plot(output_base + "/ver_residual_before_correction.png",
                      list_ver_data, height, width)


# Calculate parameters of the radial correction model
(xcenter, ycenter) = proc.find_cod_coarse(list_hor_lines, list_ver_lines)
list_fact = proc.calc_coef_backward(list_hor_lines, list_ver_lines,
                                    xcenter, ycenter, num_coef)
ycenter = 2016
xcenter = 1512
#list_fact = [ 0.9918291518692046, 4.115233807022813e-05, -4.253026568632808e-08, 1.7556318518188066e-11, -2.377025171747954e-15]

io.save_metadata_txt(output_base + "/coefficients_radial_distortion.txt",
                     xcenter, ycenter, list_fact)
print("X-center: {0}. Y-center: {1}".format(xcenter, ycenter))
print("Coefficients: {0}".format(list_fact))

"""
# Apply correction to the lines of points
list_uhor_lines = post.unwarp_line_backward(list_hor_lines, xcenter, ycenter,
                                            list_fact)
list_uver_lines = post.unwarp_line_backward(list_ver_lines, xcenter, ycenter,
                                            list_fact)
# Calculate the residual of the unwarpped points.
list_hor_data = post.calc_residual_hor(list_uhor_lines, xcenter, ycenter)
list_ver_data = post.calc_residual_ver(list_uver_lines, xcenter, ycenter)
# Save the results for checking
io.save_plot_image(output_base + "/unwarpped_horizontal_lines.png",
                   list_uhor_lines, height, width)
io.save_plot_image(output_base + "/unwarpped_vertical_lines.png",
                   list_uver_lines, height, width)
io.save_residual_plot(output_base + "/hor_residual_after_correction.png",
                      list_hor_data, height, width)
io.save_residual_plot(output_base + "/ver_residual_after_correction.png",
                      list_ver_data, height, width)
"""
# Correct the image

corrected_mat = post.unwarp_image_backward(mat0, xcenter, ycenter, list_fact)
# Save results. Note that the output is 32-bit-tif.
io.save_image(output_base + "/corrected_image.jpg", corrected_mat)
io.save_image(output_base + "/difference.jpg", corrected_mat - mat0)

exit(0)

mat1 = prep.binarization(mat0)
# Calculate the median dot size and distance between them.
(dot_size, dot_dist) = prep.calc_size_distance(mat1)
#(dot_size, dot_dist) = 30,60
dot_size, dot_dist = 451.0, 53.09686051731639
print(dot_size, dot_dist)
# Remove non-dot objects
mat1 = prep.select_dots_based_size(mat1, dot_size)
# Remove non-elliptical objects
mat1 = prep.select_dots_based_ratio(mat1)
io.save_image(output_base + "/segmented_dots.jpg", mat1) # Save image for checking
exit(0)

# Calculate the slopes of horizontal lines and vertical lines.
hor_slope = prep.calc_hor_slope(mat1)
ver_slope = prep.calc_ver_slope(mat1)
print("Horizontal slope: {0}. Vertical slope {1}".format(hor_slope, ver_slope))
