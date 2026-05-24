/* mandelbrot.c - escape-time Mandelbrot over a WIDTH x HEIGHT grid.
 *
 * For each pixel the inner loop iterates z = z^2 + c until |z|^2 > 4 or the
 * iteration cap is hit, and sums the iteration counts across all pixels. This
 * is a double-precision floating-point workload dominated by multiplies and
 * adds in the inner loop.
 *
 * Every arithmetic step is written as its own statement so the compiler does
 * not contract multiply+add into an FMA. That keeps the floating-point
 * results bit-identical to the JS, Python, and SemanticScript versions, so
 * all four report the same summed iteration count.
 *
 * Build: clang -O2 -o mandelbrot.c.exe mandelbrot.c
 */

#include <stdio.h>
#include <windows.h>

int main(void) {
    long long width = 600;
    long long height = 400;
    long long max_iterations = 1000;

    double x_min = -2.0;
    double x_max = 1.0;
    double y_min = -1.0;
    double y_max = 1.0;
    double escape_radius_squared = 4.0;

    long long total_iterations = 0;

    LARGE_INTEGER frequency;
    LARGE_INTEGER start_counter;
    LARGE_INTEGER end_counter;
    QueryPerformanceFrequency(&frequency);

    QueryPerformanceCounter(&start_counter);
    for (long long pixel_row = 0; pixel_row < height; pixel_row++) {
        double row_fraction = (double)pixel_row / (double)height;
        double imaginary_c = y_min + (y_max - y_min) * row_fraction;
        for (long long pixel_col = 0; pixel_col < width; pixel_col++) {
            double col_fraction = (double)pixel_col / (double)width;
            double real_c = x_min + (x_max - x_min) * col_fraction;

            double real_z = 0.0;
            double imaginary_z = 0.0;
            long long iteration = 0;
            while (iteration < max_iterations) {
                double real_squared = real_z * real_z;
                double imaginary_squared = imaginary_z * imaginary_z;
                double magnitude_squared = real_squared + imaginary_squared;
                if (magnitude_squared > escape_radius_squared) {
                    break;
                }
                double real_difference = real_squared - imaginary_squared;
                double next_real_z = real_difference + real_c;
                double real_times_imaginary = real_z * imaginary_z;
                double doubled_cross_term = 2.0 * real_times_imaginary;
                double next_imaginary_z = doubled_cross_term + imaginary_c;
                real_z = next_real_z;
                imaginary_z = next_imaginary_z;
                iteration++;
            }
            total_iterations += iteration;
        }
    }
    QueryPerformanceCounter(&end_counter);

    double elapsed_seconds =
        (double)(end_counter.QuadPart - start_counter.QuadPart) /
        (double)frequency.QuadPart;

    printf("checksum=%lld elapsedSeconds=%.6f\n", total_iterations,
           elapsed_seconds);
    return 0;
}
