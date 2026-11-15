/* FILE streams by name: writing, reading back, positions, pushback, end of file and errors, buffering, rename,
   remove, tmpfile, and tmpnam's form (its letters are random). */
#include <stdio.h>
#include <string.h>

int main(void) {
    FILE *out = fopen("streams-test.txt", "w");
    if (!out) return 10;
    for (int i = 0; i < 1000; i++) fprintf(out, "line %d\n", i);
    fputs("last", out);
    fputc('!', out);
    printf("ftell after writing: %ld\n", ftell(out));
    printf("fclose: %d\n", fclose(out));

    FILE *in = fopen("streams-test.txt", "r");
    char line[64];
    int lines = 0;
    while (fgets(line, sizeof line, in)) lines++;
    printf("lines %d, last [%s], feof %d, ferror %d\n", lines, line, feof(in) != 0, ferror(in) != 0);
    printf("fgetc at end: %d\n", fgetc(in));
    rewind(in);
    printf("after rewind feof %d, first byte %c\n", feof(in) != 0, fgetc(in));
    printf("ungetc %c, then %c%c\n", ungetc('X', in), fgetc(in), fgetc(in));
    fseek(in, -5, SEEK_END);
    printf("ftell %ld, read [%s]\n", ftell(in), fgets(line, sizeof line, in));
    fpos_t mark;
    fseek(in, 100, SEEK_SET);
    fgetpos(in, &mark);
    char block[12] = {0};
    printf("fread %zu [%s]\n", fread(block, 1, 11, in), block);
    fsetpos(in, &mark);
    memset(block, 0, sizeof block);
    printf("again %zu [%s] at %ld\n", fread(block, 2, 5, in), block, ftell(in));
    fseek(in, 0, SEEK_CUR);
    printf("fputc on a read stream: %d, ferror %d\n", fputc('x', in), ferror(in) != 0);
    clearerr(in);
    printf("after clearerr ferror %d\n", ferror(in) != 0);
    fclose(in);

    FILE *both = fopen("streams-test.txt", "r+");
    fseek(both, 5, SEEK_SET);
    fputs("ZERO", both);
    fseek(both, 0, SEEK_SET);
    printf("r+ [%s]", fgets(line, sizeof line, both));
    fclose(both);

    FILE *appended = fopen("streams-test.txt", "a");
    fputs("\nappended\n", appended);
    fclose(appended);
    FILE *tail = fopen("streams-test.txt", "r");
    fseek(tail, -9, SEEK_END);
    printf("tail [%s]", fgets(line, sizeof line, tail));
    fclose(tail);

    printf("rename %d\n", rename("streams-test.txt", "streams-moved.txt"));
    printf("open old name %s\n", fopen("streams-test.txt", "r") ? "found" : "missing");
    printf("remove %d\n", remove("streams-moved.txt"));
    printf("remove again %d\n", remove("streams-moved.txt"));
    printf("fopen bad mode %s\n", fopen("x", "q") ? "opened" : "refused");

    FILE *scratch = tmpfile();
    fprintf(scratch, "temporary %d", 99);
    rewind(scratch);
    int number = 0;
    printf("tmpfile scan %d -> %d\n", fscanf(scratch, "temporary %d", &number), number);
    fclose(scratch);
    char name[L_tmpnam];
    char *made = tmpnam(name);
    printf("tmpnam %s %zu\n", made == name && strncmp(name, "/tmp/file", 9) == 0 ? "ok" : "bad", strlen(name));

    FILE *unbuffered = fopen("streams-unbuffered.txt", "w");
    setvbuf(unbuffered, NULL, _IONBF, 0);
    fputs("direct", unbuffered);
    FILE *peek = fopen("streams-unbuffered.txt", "r");
    printf("unbuffered visible [%s]\n", fgets(line, sizeof line, peek));
    fclose(peek);
    fclose(unbuffered);
    remove("streams-unbuffered.txt");

    char own[64];
    FILE *full = fopen("streams-full.txt", "w");
    setbuf(full, own);
    fputs("held", full);
    FILE *look = fopen("streams-full.txt", "r");
    printf("buffered visible [%s]\n", fgets(line, sizeof line, look) ? line : "(nothing)");
    fflush(full);
    printf("after fflush [%s]\n", fgets(line, sizeof line, look) ? line : "(nothing)");
    fclose(look);
    fclose(full);
    remove("streams-full.txt");

    puts("puts line");
    putchar('c');
    putc('\n', stdout);
    fwrite("fwrite\n", 1, 7, stdout);
    fputs("err line\n", stderr);
    return 0;
}
