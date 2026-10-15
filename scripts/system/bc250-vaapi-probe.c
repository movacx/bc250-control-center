/*
 * Ask libva what a VA-API driver offers on the BC-250, from a 32-bit program.
 *
 * bc250-vaapi-probe.py does this for the 64-bit driver through ctypes. A 32-bit
 * driver can only be loaded by a 32-bit process, and SteamOS (where the 32-bit
 * companion matters, for Steam Remote Play) has no 32-bit Python, so this is the
 * same check in C, built in the 32-bit build container and run on the host: it
 * uses the host's own 32-bit libva, which is what Steam's streaming client uses.
 *
 *     bc250-vaapi-probe32 /dev/dri/renderD128
 *
 * It opens the render node, initialises the driver libva picks from
 * LIBVA_DRIVER_NAME and LIBVA_DRIVERS_PATH, and lists the H.264 and HEVC entry
 * points. One line on stdout; exit status 0 only when H.264 and HEVC both
 * encode and decode.
 */
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <va/va.h>
#include <va/va_drm.h>

int main(int argc, char **argv)
{
    const char *node = argc > 1 ? argv[1] : "/dev/dri/renderD128";
    int fd = open(node, O_RDWR);
    if (fd < 0) {
        fprintf(stderr, "%s could not be opened\n", node);
        return 2;
    }
    VADisplay display = vaGetDisplayDRM(fd);
    if (!display) {
        fprintf(stderr, "libva could not use the render node\n");
        return 2;
    }
    int major = 0, minor = 0;
    VAStatus status = vaInitialize(display, &major, &minor);
    if (status != VA_STATUS_SUCCESS) {
        fprintf(stderr, "The driver did not start (libva status %d: %s)\n", status, vaErrorStr(status));
        return 1;
    }
    const char *vendor = vaQueryVendorString(display);

    int count = vaMaxNumProfiles(display);
    VAProfile *profiles = calloc(count > 0 ? count : 1, sizeof *profiles);
    int h264_encode = 0, h264_decode = 0, hevc_encode = 0, hevc_decode = 0;
    if (profiles && vaQueryConfigProfiles(display, profiles, &count) == VA_STATUS_SUCCESS) {
        for (int i = 0; i < count; i++) {
            int h264 = profiles[i] == VAProfileH264Main || profiles[i] == VAProfileH264High ||
                       profiles[i] == VAProfileH264ConstrainedBaseline;
            int hevc = profiles[i] == VAProfileHEVCMain || profiles[i] == VAProfileHEVCMain10;
            if (!h264 && !hevc)
                continue;
            int slots = vaMaxNumEntrypoints(display);
            VAEntrypoint *entries = calloc(slots > 0 ? slots : 1, sizeof *entries);
            if (entries && vaQueryConfigEntrypoints(display, profiles[i], entries, &slots) == VA_STATUS_SUCCESS) {
                for (int j = 0; j < slots; j++) {
                    int encode = entries[j] == VAEntrypointEncSlice || entries[j] == VAEntrypointEncSliceLP;
                    int decode = entries[j] == VAEntrypointVLD;
                    h264_encode |= h264 && encode;
                    h264_decode |= h264 && decode;
                    hevc_encode |= hevc && encode;
                    hevc_decode |= hevc && decode;
                }
            }
            free(entries);
        }
    }
    free(profiles);
    vaTerminate(display);
    close(fd);

    printf("driver=\"%s\" h264_encode=%d h264_decode=%d hevc_encode=%d hevc_decode=%d\n",
           vendor ? vendor : "", h264_encode, h264_decode, hevc_encode, hevc_decode);
    return h264_encode && h264_decode && hevc_encode && hevc_decode ? 0 : 1;
}
