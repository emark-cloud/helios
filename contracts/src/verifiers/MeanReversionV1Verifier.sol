// SPDX-License-Identifier: GPL-3.0
/*
    Copyright 2021 0KIMS association.

    This file is generated with [snarkJS](https://github.com/iden3/snarkjs).

    snarkJS is a free software: you can redistribute it and/or modify it
    under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    snarkJS is distributed in the hope that it will be useful, but WITHOUT
    ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
    or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public
    License for more details.

    You should have received a copy of the GNU General Public License
    along with snarkJS. If not, see <https://www.gnu.org/licenses/>.
*/

pragma solidity >=0.7.0 <0.9.0;

contract MeanReversionV1Verifier {
    // Scalar field size
    uint256 constant r =
        21_888_242_871_839_275_222_246_405_745_257_275_088_548_364_400_416_034_343_698_204_186_575_808_495_617;
    // Base field size
    uint256 constant q =
        21_888_242_871_839_275_222_246_405_745_257_275_088_696_311_157_297_823_662_689_037_894_645_226_208_583;

    // Verification Key data
    uint256 constant alphax =
        20_491_192_805_390_485_299_153_009_773_594_534_940_189_261_866_228_447_918_068_658_471_970_481_763_042;
    uint256 constant alphay =
        9_383_485_363_053_290_200_918_347_156_157_836_566_562_967_994_039_712_273_449_902_621_266_178_545_958;
    uint256 constant betax1 =
        4_252_822_878_758_300_859_123_897_981_450_591_353_533_073_413_197_771_768_651_442_665_752_259_397_132;
    uint256 constant betax2 =
        6_375_614_351_688_725_206_403_948_262_868_962_793_625_744_043_794_305_715_222_011_528_459_656_738_731;
    uint256 constant betay1 =
        21_847_035_105_528_745_403_288_232_691_147_584_728_191_162_732_299_865_338_377_159_692_350_059_136_679;
    uint256 constant betay2 =
        10_505_242_626_370_262_277_552_901_082_094_356_697_409_835_680_220_590_971_873_171_140_371_331_206_856;
    uint256 constant gammax1 =
        11_559_732_032_986_387_107_991_004_021_392_285_783_925_812_861_821_192_530_917_403_151_452_391_805_634;
    uint256 constant gammax2 =
        10_857_046_999_023_057_135_944_570_762_232_829_481_370_756_359_578_518_086_990_519_993_285_655_852_781;
    uint256 constant gammay1 =
        4_082_367_875_863_433_681_332_203_403_145_435_568_316_851_327_593_401_208_105_741_076_214_120_093_531;
    uint256 constant gammay2 =
        8_495_653_923_123_431_417_604_973_247_489_272_438_418_190_587_263_600_148_770_280_649_306_958_101_930;
    uint256 constant deltax1 =
        7_111_752_766_313_155_402_403_129_684_365_149_111_888_013_008_469_145_651_032_332_631_160_792_114_407;
    uint256 constant deltax2 =
        8_283_338_443_784_760_126_158_352_744_514_344_680_443_998_044_773_534_222_017_363_169_725_387_256_669;
    uint256 constant deltay1 =
        10_223_489_379_483_842_923_958_042_329_466_793_299_679_220_765_613_387_391_896_478_229_829_698_643_396;
    uint256 constant deltay2 =
        11_456_425_356_917_817_849_238_617_618_420_377_018_164_231_634_656_303_182_429_622_094_915_833_805_539;

    uint256 constant IC0x =
        16_682_536_519_829_499_043_815_683_943_418_993_151_107_304_877_785_636_862_033_795_251_573_610_954_204;
    uint256 constant IC0y =
        19_972_911_520_986_420_446_590_508_686_935_607_870_942_421_372_714_345_196_449_725_118_929_142_313_460;

    uint256 constant IC1x =
        20_213_118_166_097_841_270_001_193_182_457_897_355_417_773_306_928_566_466_750_700_859_907_214_724_111;
    uint256 constant IC1y =
        4_170_979_317_180_890_264_508_357_900_543_024_024_465_462_531_500_136_262_121_703_592_370_336_247_628;

    uint256 constant IC2x =
        12_637_341_198_178_769_832_443_861_374_756_482_027_054_481_228_404_249_544_615_729_617_421_339_326_147;
    uint256 constant IC2y =
        19_677_336_765_515_743_861_688_300_635_073_320_634_593_187_391_526_681_318_397_847_482_209_524_158_952;

    uint256 constant IC3x =
        19_599_737_345_587_568_234_303_897_280_630_162_711_481_156_894_622_849_352_260_079_080_154_672_414_128;
    uint256 constant IC3y =
        3_209_362_373_809_418_956_725_501_047_470_560_459_615_803_648_954_415_921_478_560_893_223_965_248_578;

    uint256 constant IC4x =
        21_771_719_453_166_851_433_158_916_952_808_032_044_626_075_289_059_922_682_833_908_145_865_395_918_833;
    uint256 constant IC4y =
        17_081_005_912_209_770_982_884_910_956_653_335_689_329_945_586_481_014_085_563_602_539_126_103_370_319;

    uint256 constant IC5x =
        18_084_377_648_782_012_858_218_414_288_936_949_246_217_404_831_361_038_963_446_282_333_075_964_659_741;
    uint256 constant IC5y =
        1_506_945_692_315_462_919_689_646_974_293_435_609_399_637_315_773_986_528_870_533_171_197_112_726_047;

    uint256 constant IC6x =
        18_528_822_351_991_514_765_179_911_212_785_360_419_875_274_656_700_034_870_632_141_082_599_056_870_197;
    uint256 constant IC6y =
        18_569_067_153_914_051_419_252_167_477_713_541_726_226_851_854_046_295_152_049_888_238_064_510_512_857;

    uint256 constant IC7x =
        1_715_833_112_392_818_937_025_868_680_359_337_274_800_665_070_066_776_832_127_796_679_256_196_186_648;
    uint256 constant IC7y =
        3_392_791_168_470_952_626_827_291_287_626_860_361_455_631_624_902_169_901_504_756_092_112_812_958_965;

    uint256 constant IC8x =
        21_098_096_542_404_984_516_804_537_321_246_637_386_605_386_270_121_000_003_945_843_532_424_038_561_574;
    uint256 constant IC8y =
        16_474_860_959_726_392_528_217_109_098_427_172_547_753_231_170_616_144_664_652_260_477_251_607_304_505;

    uint256 constant IC9x =
        14_892_689_186_892_730_546_288_002_406_372_617_547_156_052_705_865_669_269_359_732_324_902_489_348_137;
    uint256 constant IC9y =
        8_911_879_171_916_910_797_123_118_045_709_419_492_420_117_996_151_140_578_014_155_192_670_727_956_294;

    uint256 constant IC10x =
        4_302_260_112_192_491_172_275_189_087_385_475_650_437_578_582_901_327_091_042_987_312_104_028_405_435;
    uint256 constant IC10y =
        1_430_737_497_135_096_613_440_060_607_812_699_446_693_361_435_574_831_620_692_112_166_829_324_926_419;

    uint256 constant IC11x =
        6_202_297_241_174_717_605_581_483_219_037_552_857_557_487_732_799_997_560_405_752_970_077_547_407_600;
    uint256 constant IC11y =
        13_905_235_013_985_500_208_158_600_487_171_996_159_601_511_827_999_685_092_011_544_119_815_071_917_222;

    uint256 constant IC12x =
        2_433_070_063_087_224_016_188_600_121_196_726_838_127_440_731_349_948_063_322_898_538_921_900_166_391;
    uint256 constant IC12y =
        2_492_669_173_583_640_959_748_563_953_790_692_712_630_040_509_452_658_337_595_164_074_860_526_211_673;

    uint256 constant IC13x =
        7_118_581_281_331_937_810_824_463_067_526_394_890_807_832_698_980_718_803_735_516_233_612_462_768_548;
    uint256 constant IC13y =
        17_336_812_869_500_920_623_727_743_522_896_558_178_226_607_645_020_837_655_345_714_906_375_625_706_712;

    uint256 constant IC14x =
        19_076_051_596_526_933_990_776_117_653_904_854_316_133_061_289_327_418_861_479_409_448_871_989_720_634;
    uint256 constant IC14y =
        8_784_602_901_587_726_229_121_476_871_149_323_504_863_432_964_179_754_658_337_377_615_770_444_834_209;

    uint256 constant IC15x =
        3_853_155_624_544_166_247_008_982_559_736_920_182_699_330_205_183_340_794_146_640_866_685_208_821_112;
    uint256 constant IC15y =
        12_700_505_587_834_560_275_316_888_830_193_535_317_200_536_471_435_717_436_389_674_998_260_798_263_915;

    uint256 constant IC16x =
        4_225_137_359_576_551_513_389_965_049_324_238_691_413_021_444_193_899_991_843_813_505_156_402_933_113;
    uint256 constant IC16y =
        7_764_464_430_332_464_967_095_344_251_277_606_164_491_787_013_067_740_859_066_024_928_064_971_542_353;

    // Memory data
    uint16 constant pVk = 0;
    uint16 constant pPairing = 128;

    uint16 constant pLastMem = 896;

    function verifyProof(
        uint256[2] calldata _pA,
        uint256[2][2] calldata _pB,
        uint256[2] calldata _pC,
        uint256[16] calldata _pubSignals
    ) public view returns (bool) {
        assembly {
            function checkField(v) {
                if iszero(lt(v, r)) {
                    mstore(0, 0)
                    return(0, 0x20)
                }
            }

            // G1 function to multiply a G1 value(x,y) to value in an address
            function g1_mulAccC(pR, x, y, s) {
                let success
                let mIn := mload(0x40)
                mstore(mIn, x)
                mstore(add(mIn, 32), y)
                mstore(add(mIn, 64), s)

                success := staticcall(sub(gas(), 2000), 7, mIn, 96, mIn, 64)

                if iszero(success) {
                    mstore(0, 0)
                    return(0, 0x20)
                }

                mstore(add(mIn, 64), mload(pR))
                mstore(add(mIn, 96), mload(add(pR, 32)))

                success := staticcall(sub(gas(), 2000), 6, mIn, 128, pR, 64)

                if iszero(success) {
                    mstore(0, 0)
                    return(0, 0x20)
                }
            }

            function checkPairing(pA, pB, pC, pubSignals, pMem) -> isOk {
                let _pPairing := add(pMem, pPairing)
                let _pVk := add(pMem, pVk)

                mstore(_pVk, IC0x)
                mstore(add(_pVk, 32), IC0y)

                // Compute the linear combination vk_x

                g1_mulAccC(_pVk, IC1x, IC1y, calldataload(add(pubSignals, 0)))

                g1_mulAccC(_pVk, IC2x, IC2y, calldataload(add(pubSignals, 32)))

                g1_mulAccC(_pVk, IC3x, IC3y, calldataload(add(pubSignals, 64)))

                g1_mulAccC(_pVk, IC4x, IC4y, calldataload(add(pubSignals, 96)))

                g1_mulAccC(_pVk, IC5x, IC5y, calldataload(add(pubSignals, 128)))

                g1_mulAccC(_pVk, IC6x, IC6y, calldataload(add(pubSignals, 160)))

                g1_mulAccC(_pVk, IC7x, IC7y, calldataload(add(pubSignals, 192)))

                g1_mulAccC(_pVk, IC8x, IC8y, calldataload(add(pubSignals, 224)))

                g1_mulAccC(_pVk, IC9x, IC9y, calldataload(add(pubSignals, 256)))

                g1_mulAccC(_pVk, IC10x, IC10y, calldataload(add(pubSignals, 288)))

                g1_mulAccC(_pVk, IC11x, IC11y, calldataload(add(pubSignals, 320)))

                g1_mulAccC(_pVk, IC12x, IC12y, calldataload(add(pubSignals, 352)))

                g1_mulAccC(_pVk, IC13x, IC13y, calldataload(add(pubSignals, 384)))

                g1_mulAccC(_pVk, IC14x, IC14y, calldataload(add(pubSignals, 416)))

                g1_mulAccC(_pVk, IC15x, IC15y, calldataload(add(pubSignals, 448)))

                g1_mulAccC(_pVk, IC16x, IC16y, calldataload(add(pubSignals, 480)))

                // -A
                mstore(_pPairing, calldataload(pA))
                mstore(add(_pPairing, 32), mod(sub(q, calldataload(add(pA, 32))), q))

                // B
                mstore(add(_pPairing, 64), calldataload(pB))
                mstore(add(_pPairing, 96), calldataload(add(pB, 32)))
                mstore(add(_pPairing, 128), calldataload(add(pB, 64)))
                mstore(add(_pPairing, 160), calldataload(add(pB, 96)))

                // alpha1
                mstore(add(_pPairing, 192), alphax)
                mstore(add(_pPairing, 224), alphay)

                // beta2
                mstore(add(_pPairing, 256), betax1)
                mstore(add(_pPairing, 288), betax2)
                mstore(add(_pPairing, 320), betay1)
                mstore(add(_pPairing, 352), betay2)

                // vk_x
                mstore(add(_pPairing, 384), mload(add(pMem, pVk)))
                mstore(add(_pPairing, 416), mload(add(pMem, add(pVk, 32))))

                // gamma2
                mstore(add(_pPairing, 448), gammax1)
                mstore(add(_pPairing, 480), gammax2)
                mstore(add(_pPairing, 512), gammay1)
                mstore(add(_pPairing, 544), gammay2)

                // C
                mstore(add(_pPairing, 576), calldataload(pC))
                mstore(add(_pPairing, 608), calldataload(add(pC, 32)))

                // delta2
                mstore(add(_pPairing, 640), deltax1)
                mstore(add(_pPairing, 672), deltax2)
                mstore(add(_pPairing, 704), deltay1)
                mstore(add(_pPairing, 736), deltay2)

                let success := staticcall(sub(gas(), 2000), 8, _pPairing, 768, _pPairing, 0x20)

                isOk := and(success, mload(_pPairing))
            }

            let pMem := mload(0x40)
            mstore(0x40, add(pMem, pLastMem))

            // Validate that all evaluations ∈ F

            checkField(calldataload(add(_pubSignals, 0)))

            checkField(calldataload(add(_pubSignals, 32)))

            checkField(calldataload(add(_pubSignals, 64)))

            checkField(calldataload(add(_pubSignals, 96)))

            checkField(calldataload(add(_pubSignals, 128)))

            checkField(calldataload(add(_pubSignals, 160)))

            checkField(calldataload(add(_pubSignals, 192)))

            checkField(calldataload(add(_pubSignals, 224)))

            checkField(calldataload(add(_pubSignals, 256)))

            checkField(calldataload(add(_pubSignals, 288)))

            checkField(calldataload(add(_pubSignals, 320)))

            checkField(calldataload(add(_pubSignals, 352)))

            checkField(calldataload(add(_pubSignals, 384)))

            checkField(calldataload(add(_pubSignals, 416)))

            checkField(calldataload(add(_pubSignals, 448)))

            checkField(calldataload(add(_pubSignals, 480)))

            // Validate all evaluations
            let isValid := checkPairing(_pA, _pB, _pC, _pubSignals, pMem)

            mstore(0, isValid)
            return(0, 0x20)
        }
    }
}
