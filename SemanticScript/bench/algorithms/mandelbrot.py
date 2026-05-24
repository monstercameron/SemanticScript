"""mandelbrot.py - escape-time Mandelbrot over a WIDTH x HEIGHT grid.

Mirrors mandelbrot.c exactly: same grid, same iteration cap, same order of
floating-point operations (separate temporaries, no FMA), so the summed
iteration-count checksum is identical across all four languages.
Timed with time.perf_counter().
"""

import time


def main():
    width = 600
    height = 400
    max_iterations = 1000

    x_min = -2.0
    x_max = 1.0
    y_min = -1.0
    y_max = 1.0
    escape_radius_squared = 4.0

    total_iterations = 0

    start = time.perf_counter()
    for pixel_row in range(height):
        row_fraction = pixel_row / height
        imaginary_c = y_min + (y_max - y_min) * row_fraction
        for pixel_col in range(width):
            col_fraction = pixel_col / width
            real_c = x_min + (x_max - x_min) * col_fraction

            real_z = 0.0
            imaginary_z = 0.0
            iteration = 0
            while iteration < max_iterations:
                real_squared = real_z * real_z
                imaginary_squared = imaginary_z * imaginary_z
                magnitude_squared = real_squared + imaginary_squared
                if magnitude_squared > escape_radius_squared:
                    break
                real_difference = real_squared - imaginary_squared
                next_real_z = real_difference + real_c
                real_times_imaginary = real_z * imaginary_z
                doubled_cross_term = 2.0 * real_times_imaginary
                next_imaginary_z = doubled_cross_term + imaginary_c
                real_z = next_real_z
                imaginary_z = next_imaginary_z
                iteration += 1
            total_iterations += iteration
    end = time.perf_counter()

    elapsed_seconds = end - start
    print(f"checksum={total_iterations} elapsedSeconds={elapsed_seconds:.6f}")


if __name__ == "__main__":
    main()
