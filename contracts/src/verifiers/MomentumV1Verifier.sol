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
        8_510_309_489_208_220_795_261_815_750_090_423_590_058_925_030_663_187_075_333_523_777_788_372_425_989;
    uint256 constant deltax2 =
        10_246_849_382_386_886_905_325_193_554_585_493_353_559_553_196_711_592_920_262_851_985_870_894_058_021;
    uint256 constant deltay1 =
        18_971_978_011_595_193_560_188_312_776_785_991_836_298_961_203_794_505_623_834_839_979_505_745_179_070;
    uint256 constant deltay2 =
        20_374_213_101_816_055_204_277_584_342_187_892_686_035_929_664_977_564_739_834_405_443_886_030_499_106;

    uint256 constant IC0x =
        19_655_889_773_309_054_432_344_258_881_073_239_562_391_871_918_795_268_377_316_762_776_802_511_321_321;
    uint256 constant IC0y =
        3_562_625_032_433_508_950_210_293_231_089_049_638_410_927_541_194_037_691_258_392_422_475_624_629_429;

    uint256 constant IC1x =
        17_450_968_865_143_286_177_113_245_664_719_827_880_317_434_237_712_601_025_807_119_261_050_626_800_483;
    uint256 constant IC1y =
        14_956_546_518_249_010_768_102_658_514_586_686_599_002_510_420_755_217_565_073_879_161_646_298_430_340;

    uint256 constant IC2x =
        9_530_110_093_824_184_092_366_980_248_854_388_931_377_241_893_540_347_643_923_914_949_684_250_114_885;
    uint256 constant IC2y =
        1_715_069_246_643_424_096_055_086_485_779_890_399_452_400_505_281_304_303_102_309_696_550_585_320_833;

    uint256 constant IC3x =
        20_197_699_211_740_763_418_249_210_318_111_230_576_441_586_624_756_532_412_090_599_489_338_365_477_775;
    uint256 constant IC3y =
        3_384_878_660_857_506_024_977_546_536_526_968_849_430_865_614_773_753_456_693_894_612_782_563_623_832;

    uint256 constant IC4x =
        13_890_094_510_383_343_316_466_144_367_868_945_893_070_178_119_633_790_491_884_111_206_542_037_220_887;
    uint256 constant IC4y =
        17_795_370_933_461_381_225_065_735_062_354_729_907_344_435_724_677_608_658_782_992_578_464_469_301_121;

    uint256 constant IC5x =
        13_475_438_243_364_198_425_806_858_411_408_123_344_133_564_190_022_147_111_950_438_812_724_174_689_423;
    uint256 constant IC5y =
        15_698_210_016_077_568_854_934_780_786_047_631_918_501_917_208_281_220_312_444_533_780_729_283_638_603;

    uint256 constant IC6x =
        9_148_554_011_700_985_519_713_263_573_199_274_519_643_530_007_936_174_167_335_149_462_784_881_004_772;
    uint256 constant IC6y =
        4_974_096_783_383_263_422_770_175_336_340_354_162_588_326_735_337_487_763_089_387_814_808_753_320_466;

    uint256 constant IC7x =
        11_023_921_833_603_113_398_052_451_777_546_314_063_394_574_229_380_045_354_083_938_993_556_571_989_724;
    uint256 constant IC7y =
        14_937_985_418_804_545_321_609_131_221_703_871_093_503_345_116_240_266_249_880_439_835_859_651_238_168;

    uint256 constant IC8x =
        13_650_522_615_609_288_737_057_923_038_885_359_769_153_250_604_087_338_643_444_761_468_247_006_623_086;
    uint256 constant IC8y =
        12_146_989_624_937_409_603_289_823_173_703_194_208_820_870_206_614_903_944_779_111_193_080_037_222_826;

    uint256 constant IC9x =
        16_322_772_471_838_071_985_643_762_927_007_990_855_587_985_027_948_833_836_052_939_518_095_138_784_797;
    uint256 constant IC9y =
        11_929_759_242_326_662_882_027_345_604_253_865_971_498_358_044_139_972_224_228_219_134_417_832_847_194;

    uint256 constant IC10x =
        4_788_170_925_912_328_812_891_963_668_107_311_424_368_287_313_785_098_163_558_744_441_869_119_204_984;
    uint256 constant IC10y =
        16_258_257_559_176_131_728_758_956_033_941_824_569_607_952_860_956_123_735_240_906_003_652_379_330_241;

    uint256 constant IC11x =
        5_304_895_755_373_634_262_300_495_697_358_022_722_213_334_666_224_723_817_268_386_128_425_056_211_622;
    uint256 constant IC11y =
        524_585_492_706_183_167_356_200_222_452_977_811_330_015_935_867_678_177_642_916_922_438_708_466_819;

    uint256 constant IC12x =
        13_033_738_808_580_651_643_508_144_658_024_857_923_016_393_624_955_455_891_010_541_657_334_625_175_352;
    uint256 constant IC12y =
        10_219_818_829_116_510_107_543_310_161_865_330_607_294_538_533_281_672_292_667_301_620_629_418_438_961;

    uint256 constant IC13x =
        8_814_996_571_259_682_800_994_216_620_953_539_365_693_296_028_509_198_665_030_952_914_857_866_409_264;
    uint256 constant IC13y =
        6_474_746_830_316_073_462_712_565_255_528_949_900_924_563_019_254_177_103_178_536_954_893_704_796_179;

    uint256 constant IC14x =
        19_614_460_366_687_009_899_064_657_935_048_188_934_599_899_940_161_322_467_117_983_646_752_789_790_168;
    uint256 constant IC14y =
        19_130_147_463_600_167_521_751_151_864_037_851_382_106_740_531_146_051_646_064_331_161_024_553_637_446;

    // Memory data
    uint16 constant pVk = 0;
    uint16 constant pPairing = 128;

    uint16 constant pLastMem = 896;

    function verifyProof(
        uint256[2] calldata _pA,
        uint256[2][2] calldata _pB,
        uint256[2] calldata _pC,
        uint256[14] calldata _pubSignals
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

            // Validate all evaluations
            let isValid := checkPairing(_pA, _pB, _pC, _pubSignals, pMem)

            mstore(0, isValid)
            return(0, 0x20)
        }
    }
}
