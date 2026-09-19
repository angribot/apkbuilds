#include <stdio.h>

int main(int argc, char **argv)
{
    const char *path = argc == 2
        ? argv[1] : "/usr/share/apkbuilds-ci-probe/message.txt";
    FILE *input = fopen(path, "r");
    char message[64];
    if (input == NULL) {
        perror(path);
        return 1;
    }
    if (fgets(message, sizeof(message), input) == NULL) {
        fclose(input);
        return 1;
    }
    fclose(input);
    printf("apkbuilds-ci-probe: %s", message);
    return 0;
}
