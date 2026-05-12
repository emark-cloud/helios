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

contract MomentumV1Verifier {
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
        14_716_327_031_164_233_914_432_871_405_457_150_211_084_909_190_319_019_846_738_640_539_401_264_063_265;
    uint256 constant deltax2 =
        18_772_734_358_361_163_788_040_829_501_310_379_495_532_681_670_367_819_245_640_150_266_534_876_839_196;
    uint256 constant deltay1 =
        10_021_398_193_376_580_341_268_747_396_835_125_363_282_994_932_310_869_645_843_580_306_227_611_911_576;
    uint256 constant deltay2 =
        18_902_462_895_260_577_238_359_754_726_544_181_686_901_347_256_668_650_163_012_040_240_832_976_584_736;

    uint256 constant IC0x =
        14_485_340_958_498_515_998_178_034_897_396_991_988_025_434_800_050_225_237_206_865_965_845_225_552_088;
    uint256 constant IC0y =
        18_497_244_045_056_540_451_244_721_629_307_252_430_050_347_666_114_770_963_877_955_901_603_886_855_383;

    uint256 constant IC1x =
        21_182_376_400_623_139_940_740_495_967_336_263_157_831_564_833_834_733_476_839_697_230_654_877_963_567;
    uint256 constant IC1y =
        11_540_447_467_700_060_968_876_182_099_074_016_502_560_448_294_589_116_022_155_494_672_644_056_853_696;

    uint256 constant IC2x =
        3_345_093_992_537_341_852_762_739_827_217_317_429_528_402_710_350_615_004_818_445_173_560_639_013_013;
    uint256 constant IC2y =
        17_633_024_535_466_795_789_209_002_153_755_136_243_320_875_763_901_675_313_825_600_954_310_651_981_746;

    uint256 constant IC3x =
        19_655_247_968_227_373_403_934_253_121_798_339_848_457_557_091_624_577_378_539_445_110_701_774_526_165;
    uint256 constant IC3y =
        20_663_918_066_466_561_334_969_864_363_010_114_629_508_168_514_758_905_851_723_941_271_472_821_477_712;

    uint256 constant IC4x =
        8_573_406_284_371_350_460_524_437_598_163_507_553_120_694_007_429_202_340_217_141_680_301_240_046_939;
    uint256 constant IC4y =
        9_267_910_291_038_707_769_995_907_162_512_690_795_790_307_079_308_762_351_427_845_016_855_828_795_951;

    uint256 constant IC5x =
        8_464_083_517_300_528_306_319_143_762_945_093_327_523_763_049_128_614_983_469_065_685_569_650_438_255;
    uint256 constant IC5y =
        10_151_724_303_013_647_408_863_757_225_696_764_812_481_552_901_122_221_297_079_775_021_869_116_364_333;

    uint256 constant IC6x =
        17_901_051_646_841_609_648_448_069_386_588_926_376_170_421_153_262_729_851_416_810_539_314_915_986_389;
    uint256 constant IC6y =
        20_084_442_579_803_863_828_461_302_438_844_072_005_544_513_564_839_873_115_462_331_644_722_815_913_232;

    uint256 constant IC7x =
        21_448_733_647_087_216_918_970_039_975_007_255_557_005_167_726_335_514_515_382_649_767_332_104_696_682;
    uint256 constant IC7y =
        21_865_786_704_837_832_064_160_056_624_312_168_627_146_354_591_643_075_811_927_379_794_168_556_267_049;

    uint256 constant IC8x =
        10_960_229_711_011_529_204_537_602_407_108_205_486_003_592_368_266_744_826_015_688_270_387_323_762_115;
    uint256 constant IC8y =
        7_302_591_104_502_203_668_304_383_872_099_638_590_641_081_793_746_704_602_138_353_766_081_624_056_125;

    uint256 constant IC9x =
        8_988_359_295_618_027_081_312_886_317_898_775_345_688_544_448_321_056_411_535_212_394_771_545_604_226;
    uint256 constant IC9y =
        19_929_017_771_979_954_336_171_419_360_058_964_784_952_472_016_615_683_002_014_551_640_078_243_059_026;

    uint256 constant IC10x =
        18_801_324_185_380_708_274_146_089_183_296_067_596_790_165_578_564_940_939_790_307_592_911_569_261_891;
    uint256 constant IC10y =
        18_984_607_075_490_827_996_391_118_367_535_717_502_374_120_667_433_012_051_681_721_034_885_279_912_616;

    uint256 constant IC11x =
        19_993_076_427_213_695_975_748_599_101_803_931_002_680_426_426_051_539_363_709_162_559_932_118_774_531;
    uint256 constant IC11y =
        2_356_058_080_448_691_499_173_567_849_858_397_485_479_178_428_217_690_489_819_414_120_178_323_862_585;

    uint256 constant IC12x =
        7_076_816_899_864_292_800_268_089_353_898_378_891_014_660_911_767_980_752_936_912_849_813_310_887_386;
    uint256 constant IC12y =
        13_071_332_558_167_377_583_667_332_388_342_447_896_560_370_028_725_527_677_009_750_896_231_175_316_047;

    uint256 constant IC13x =
        20_997_064_999_208_437_475_223_479_572_142_176_417_863_648_809_194_832_931_014_308_888_294_731_095_272;
    uint256 constant IC13y =
        16_000_219_876_816_065_599_152_404_792_680_155_832_799_478_107_809_270_372_866_494_056_783_563_870_655;

    uint256 constant IC14x =
        3_326_687_020_470_531_677_962_448_749_510_207_505_284_471_782_161_769_096_613_860_222_111_041_520_774;
    uint256 constant IC14y =
        7_938_529_451_172_502_927_588_659_768_840_598_122_964_085_912_735_348_660_196_875_268_948_906_713_409;

    uint256 constant IC15x =
        12_520_111_228_204_452_720_986_167_081_604_821_105_398_733_447_712_569_310_937_091_658_519_690_882_272;
    uint256 constant IC15y =
        4_745_852_742_999_859_909_704_609_192_837_872_140_059_615_157_649_092_668_567_636_862_780_644_205_287;

    uint256 constant IC16x =
        20_614_297_103_661_610_951_604_338_292_983_182_799_094_793_491_890_856_841_613_403_041_615_327_755_151;
    uint256 constant IC16y =
        8_535_480_923_302_417_376_211_981_514_198_665_460_492_227_050_530_849_371_234_324_399_823_039_539_072;

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
