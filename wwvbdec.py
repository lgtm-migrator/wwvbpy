# SPDX-FileCopyrightText: 2021 Jeff Epler
#
# SPDX-License-Identifier: GPL-3.0-or-later

import wwvblib

# State 1: Unsync'd
#  Marker: State 2
#  Other: State 1
# State 2: One marker
#  Marker: State 3
#  Other: State 1
# State 3: Two markers
#  Marker: State 3
#  Other: State 4
# State 4: Decoding a minute, starting in second 1
#  Second

always_zero = set((4, 10, 11, 14, 20, 21, 34, 35, 44, 54))


def wwvbreceive():
    minute = []
    state = 1

    value = yield None
    while True:
        # print(state, value, len(minute), "".join(str(int(i)) for i in minute))
        if state == 1:
            minute = []
            if value == wwvblib.AmplitudeModulation.MARK:
                state = 2
            value = yield None

        elif state == 2:
            if value == wwvblib.AmplitudeModulation.MARK:
                state = 3
            else:
                state = 1
            value = yield None

        elif state == 3:
            if value != wwvblib.AmplitudeModulation.MARK:
                state = 4
                minute = [wwvblib.AmplitudeModulation.MARK, value]
            value = yield None

        elif state == 4:
            minute.append(value)
            if len(minute) % 10 == 0 and value != wwvblib.AmplitudeModulation.MARK:
                # print("MISSING MARK", len(minute), "".join(str(int(i)) for i in minute))
                state = 1
            elif len(minute) % 10 and value == wwvblib.AmplitudeModulation.MARK:
                # print("UNEXPECTED MARK")
                state = 1
            elif (
                len(minute) - 1 in always_zero
                and value != wwvblib.AmplitudeModulation.ZERO
            ):
                # print("UNEXPECTED NONZERO")
                state = 1
            elif len(minute) == 60:
                # print("FULL MINUTE")
                tc = wwvblib.WWVBTimecode(60)
                tc.am[:] = minute
                minute = []
                state = 2
                value = yield tc
            else:
                value = yield None
