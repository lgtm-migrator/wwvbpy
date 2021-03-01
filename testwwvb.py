#!/usr/bin/python3
"""Test most wwvblib functionality"""

# Copyright (C) 2011-2020 Jeff Epler <jepler@gmail.com>
# SPDX-FileCopyrightText: 2021 Jeff Epler
#
# SPDX-License-Identifier: GPL-3.0-or-later

import copy
import datetime
import glob
import io
import random
import unittest

import iersdata
import wwvblib
import wwvbdec
import uwwvb


class WWVBTestCase(unittest.TestCase):
    """Test each expected output in tests/.  Some outputs are from another program, some are from us"""

    maxDiff = 131072

    def test_cases(self):
        """Generate a test case for each expected output in tests/"""
        for test in glob.glob("tests/*"):
            with self.subTest(test=test):
                with open(test) as f:
                    text = f.read()
                lines = [line for line in text.split("\n") if not line.startswith("#")]
                while not lines[0]:
                    del lines[0]
                text = "\n".join(lines)
                header = lines[0].split()
                timestamp = " ".join(header[:10])
                options = header[10:]
                channel = "amplitude"
                style = "default"
                for o in options:
                    if o.startswith("--channel="):
                        channel = o[10:]
                    elif o.startswith("--style="):
                        style = o[8:]
                    else:  # pragma: no cover
                        raise ValueError("Unknown option %r" % o)
                num_minutes = len(lines) - 2
                if channel == "both":
                    num_minutes = len(lines) // 3
                w = wwvblib.WWVBMinute.fromstring(timestamp)
                result = io.StringIO()
                wwvblib.print_timecodes(
                    w, num_minutes, channel=channel, style=style, file=result
                )
                result = result.getvalue()
                self.assertEqual(text, result)


class WWVBRoundtrip(unittest.TestCase):
    """Round-trip tests"""

    def test_decode(self):
        """Test that a range of minutes including a leap second are correctly decoded by the state-based decoder"""
        minute = wwvblib.WWVBMinuteIERS.from_datetime(
            datetime.datetime(1992, 6, 30, 23, 50)
        )
        decoder = wwvbdec.wwvbreceive()
        next(decoder)
        decoder.send(wwvblib.AmplitudeModulation.MARK)
        any_leap_second = False
        for _ in range(20):
            timecode = minute.as_timecode()
            decoded = None
            if len(timecode.am) == 61:
                any_leap_second = True
            for code in timecode.am:
                decoded = decoder.send(code) or decoded
            self.assertEqual(
                timecode.am[:60],
                decoded.am,
                f"Checking equality of minute {minute}: [expected] {timecode.am} != [actual] {decoded.am}",
            )
            minute = minute.next_minute()
        self.assertTrue(any_leap_second)

    def test_roundtrip(self):
        """Test that a wide of minutes are correctly decoded by the state-based decoder"""
        dt = datetime.datetime(1992, 1, 1, 0, 0)
        while dt.year < 1993:
            minute = wwvblib.WWVBMinuteIERS.from_datetime(dt)
            timecode = minute.as_timecode().am
            decoded = (
                wwvblib.WWVBMinuteIERS.from_timecode_am(minute.as_timecode())
                .as_timecode()
                .am
            )
            self.assertEqual(
                timecode,
                decoded,
                f"Checking equality of minute {minute}: [expected] {timecode} != [actual] {decoded}",
            )
            dt = dt + datetime.timedelta(minutes=915)

    def test_noise(self):
        """Test against pseudorandom noise"""
        minute = wwvblib.WWVBMinuteIERS.from_datetime(
            datetime.datetime(1992, 6, 30, 23, 50)
        )
        r = random.Random(408)
        junk = [
            r.choice(
                [
                    wwvblib.AmplitudeModulation.MARK,
                    wwvblib.AmplitudeModulation.ONE,
                    wwvblib.AmplitudeModulation.ZERO,
                ]
            )
            for _ in range(480)
        ]
        timecode = minute.as_timecode()
        test_input = junk + [wwvblib.AmplitudeModulation.MARK] + timecode.am
        decoder = wwvbdec.wwvbreceive()
        next(decoder)
        for code in test_input[:-1]:
            decoded = decoder.send(code)
            self.assertIsNone(decoded)
        decoded = decoder.send(wwvblib.AmplitudeModulation.MARK)
        self.assertIsNotNone(decoded)
        self.assertEqual(
            timecode.am[:60],
            decoded.am,
            f"Checking equality of minute {minute}: [expected] {timecode.am} != [actual] {decoded.am}",
        )

    def test_noise2(self):
        """Test of the full minute decoder with targeted errors to get full coverage"""
        minute = wwvblib.WWVBMinuteIERS.from_datetime(
            datetime.datetime(2012, 6, 30, 23, 50)
        )
        timecode = minute.as_timecode()
        decoded = wwvblib.WWVBMinute.from_timecode_am(timecode)
        self.assertIsNotNone(decoded)
        for position in uwwvb.always_mark:
            test_input = copy.deepcopy(timecode)
            for noise in (0, 1):
                test_input.am[position] = wwvblib.AmplitudeModulation(noise)
                decoded = wwvblib.WWVBMinute.from_timecode_am(test_input)
                self.assertIsNone(decoded)
        for position in uwwvb.always_zero:
            test_input = copy.deepcopy(timecode)
            for noise in (1, 2):
                test_input.am[position] = wwvblib.AmplitudeModulation(noise)
                decoded = wwvblib.WWVBMinute.from_timecode_am(test_input)
                self.assertIsNone(decoded)
        for i in range(8):
            if i in (0b101, 0b010):  # Test the 6 impossible bit-combos
                continue
            test_input = copy.deepcopy(timecode)
            test_input.am[36] = wwvblib.AmplitudeModulation(i & 1)
            test_input.am[37] = wwvblib.AmplitudeModulation((i >> 1) & 1)
            test_input.am[38] = wwvblib.AmplitudeModulation((i >> 2) & 1)
            decoded = wwvblib.WWVBMinute.from_timecode_am(test_input)
            self.assertIsNone(decoded)
        # Invalid year-day
        test_input = timecode.am[:]
        test_input[22] = 1
        test_input[23] = 1
        test_input[25] = 1
        test_input[26] = 1
        test_input[27] = 1
        decoded = uwwvb.decode_wwvb(test_input)
        self.assertIsNone(decoded)

    def test_previous_next_minute(self):
        """Test that previous minute and next minute are inverses"""
        minute = wwvblib.WWVBMinuteIERS.from_datetime(
            datetime.datetime(1992, 6, 30, 23, 50)
        )
        self.assertEqual(minute, minute.next_minute().previous_minute())

    def test_data(self):
        """Test that the .data property is the same as .am (strictly for coverage)"""
        minute = wwvblib.WWVBMinuteIERS.from_datetime(
            datetime.datetime(1992, 6, 30, 23, 50)
        )
        self.assertEqual(minute.as_timecode().data, minute.as_timecode().am)

    def test_timecode_str(self):
        """Test the str() and repr() methods"""
        minute = wwvblib.WWVBMinuteIERS.from_datetime(
            datetime.datetime(1992, 6, 30, 23, 50)
        )
        timecode = minute.as_timecode()
        self.assertEqual(
            str(timecode),
            "₂₁⁰¹⁰₀⁰⁰₀²₀₀₁₀₀⁰₀¹¹₂₀⁰⁰¹₀₁⁰⁰₀₂₀⁰₁⁰₀₀⁰₁⁰²⁰¹¹₀⁰¹₀⁰¹²⁰⁰¹₀₀¹₁₁₁₂",
        )
        timecode.phase = [wwvblib.PhaseModulation.UNSET] * 60
        self.assertEqual(
            repr(timecode),
            "<WWVBTimecode 210100000200100001120001010002001000010201100100120010011112>",
        )

    def test_extreme_dut1(self):
        """Test extreme dut1 dates"""
        s = iersdata.DUT1_DATA_START
        sm1 = s - datetime.timedelta(days=1)
        self.assertEqual(wwvblib.get_dut1(s), wwvblib.get_dut1(sm1))

        e = iersdata.DUT1_DATA_START + datetime.timedelta(
            days=len(iersdata.DUT1_OFFSETS) - 1
        )
        ep1 = e + datetime.timedelta(days=1)

        self.assertEqual(wwvblib.get_dut1(e), wwvblib.get_dut1(ep1))

    def test_epoch(self):
        """Test the 1970-to-2069 epoch"""
        m = wwvblib.WWVBMinute(69, 1, 1, 0, 0)
        n = wwvblib.WWVBMinute(2069, 1, 1, 0, 0)
        self.assertEqual(m, n)

        m = wwvblib.WWVBMinute(70, 1, 1, 0, 0)
        n = wwvblib.WWVBMinute(1970, 1, 1, 0, 0)
        self.assertEqual(m, n)


if __name__ == "__main__":  # pragma no cover
    unittest.main()
